import numpy as np
import time
from pynq import DefaultIP, MMIO

class Comblock(DefaultIP):
    """
    Driver for the ICTP Comblock IP core (https://gitlab.com/rodrigomelo9/core-comblock/-/tree/master).
    
    This class maps the AXI-Lite and AXI-Full interfaces of the Comblock to 
    organized Python objects for Registers, FIFOs, and DRAM.

    Attributes
    ----------
    properties : dict
        A dictionary containing the hardware configuration parameters of the 
        Comblock.

    The following attributes are conditionally available based on the 
    specifications in 'properties':

    IN_REGS : Register
        Object providing methods to read from the input registers 
        (FPGA to CPU). Available if 'REGS_IN_ENA' is true.

    OUT_REGS : Register
        Object providing methods to read from and write to the output 
        registers (CPU to FPGA). Available if 'REGS_OUT_ENA' is true.

    FIFO_IN : Fifo
        Object providing methods to read data from the input FIFO 
        buffer (FPGA to CPU). Available if 'FIFO_IN_ENA' is true.

    FIFO_OUT : Fifo
        Object providing methods to write data to the output FIFO 
        buffer (CPU to FPGA). Available if 'FIFO_OUT_ENA' is true.

    DRAM : Dram
        Object providing methods for high-speed bulk reading and writing 
        to the shared DRAM via AXI-Full. Available if 'DRAM_IO_ENA' is true.
    """
    bindto = ['www.ictp.it:user:comblock:2.0']
    
    def __init__(self, description):
        """
        Initializes the Comblock instance by parsing IP parameters and mapping MMIO regions.

        Parameters:
            description (dict): A dictionary containing the IP's metadata and hardware parameters.
        """
        super().__init__(description=description)
        self.properties = description["parameters"]
        
        # Helper func to convert Hex strings to Integers for the axil and axif addr
        def get_addr(param):
            val = self.properties.get(param)
            return int(val, 16) if val else None

        # Setup AXIL addr
        axil_base = get_addr('C_AXIL_BASEADDR')
        axil_high = get_addr('C_AXIL_HIGHADDR')
        
        if axil_base is not None:
            axil_range = axil_high - axil_base + 1
            self.axil_mmio = MMIO(axil_base, axil_range)
            
            if self.properties['REGS_IN_ENA'] == "true":
                self.IN_REGS = Register("in", int(self.properties["REGS_IN_DEPTH"]), self.axil_mmio)

            if self.properties['REGS_OUT_ENA'] == "true":
                self.OUT_REGS = Register("out", int(self.properties["REGS_OUT_DEPTH"]), self.axil_mmio)

            if self.properties['FIFO_IN_ENA'] == "true":
                self.FIFO_IN = Fifo("in", int(self.properties["FIFO_IN_DEPTH"]), self.axil_mmio)

            if self.properties['FIFO_OUT_ENA'] == "true":
                self.FIFO_OUT = Fifo("out", int(self.properties["FIFO_OUT_DEPTH"]), self.axil_mmio)
        
        # Setup AXIF 
        if self.properties['DRAM_IO_ENA'] == "true":
            axif_base = get_addr('C_AXIF_BASEADDR')
            axif_high = get_addr('C_AXIF_HIGHADDR')
            
            if axif_base is not None:
                axif_range = axif_high - axif_base + 1               
                self.axif_mmio = MMIO(axif_base, axif_range)
                
                awidth = int(self.properties.get("DRAM_IO_AWIDTH"))
                self.DRAM = Dram(awidth, self.axif_mmio)
                
class Register:
    """
    Interface for Comblock registers.

    Parameters:
            kind (str): Either "in" (FPGA to CPU) or "out" (CPU to FPGA).
            depth (int): The number of registers available.
            mmio (pynq.MMIO): The MMIO object for the AXI-Lite interface.
    """
    def __init__(self, kind, depth, mmio):
        self.mmio = mmio
        self.depth = depth
        self.kind = kind
        self._base = 0 if kind == "in" else 16 * 4

    def write(self, offset, value): 
        """
        Writes a 32-bit value to a specific register offset.

        Parameters:
            offset (int): The register index (0 to depth-1).
            value (int/float): The value to write (cast to 32-bit int).
            
        Raises:
            PermissionError: If called on an Input Register.
            IndexError: If offset value is out of range.
        """
        # Validate Access Rights
        if self.kind == "in":
            raise PermissionError("Input Register is read-only")
        
        # Validate the Offset
        if offset < 0 or offset >= self.depth:
            raise IndexError(f"Register offset {offset} out of range (depth: {self.depth})")

        self.mmio.write(self._base + (offset * 4), int(value))

    def read(self, offset): 
        """
        Reads a 32-bit value from a specific register offset.

        Parameters:
            offset (int): The register index (0 to depth-1).

        Returns:
            int: The 32-bit value stored in the register.

        Raises:
            IndexError: If offset value is out of range.
        """
        # Validate the Offset
        if offset > 15:
            return IndexError("Incorrect memory address, verify 'offset' parameter")
        elif offset > self.depth:
            return IndexError(f"Register offset {offset} out of range (depth: {self.depth})")

        return self.mmio.read(self._base + (offset * 4))
    
class Fifo:
    """
    Interface for Comblock FIFO buffers.

    Parameters:
            kind (str): Either "in" (FPGA to CPU) or "out" (CPU to FPGA).
            depth (int): Total capacity of the FIFO.
            mmio (pynq.MMIO): The MMIO object for the AXI-Lite interface.
    """
    def __init__(self, kind, depth, mmio):
        self.mmio = mmio
        self.kind = kind
        self.depth = depth

        # Standar OFFSETS for Comblock
        self._offset_val = 32 if kind == "in" else 36
        self._addr_val = self._offset_val * 4
        self._addr_ctrl = (self._offset_val + 1) * 4
        self._addr_stat = (self._offset_val + 2) * 4

    def get_status(self):
        """
        Reads and decodes the FIFO status register into a readable dictionary.
        
        Returns:
            dict: A dictionary containing the following keys:
                - 'occupancy' (int): Number of 32-bit words currently in the FIFO.
                - 'empty' (int): 1 if the FIFO is empty, 0 otherwise.
                - 'full' (int): 1 if the FIFO is full, 0 otherwise.
                - 'almost_empty' (int): 1 if occupancy is below the threshold.
                - 'almost_full' (int): 1 if occupancy is above the threshold.
                - 'underflow' (int): 1 if a read was attempted on an empty FIFO.
                - 'overflow' (int): 1 if a write was attempted on a full FIFO.
        """
        # Read the raw 32-bit register
        stat = self.mmio.read(self._addr_stat)
        
        # Extract the two main components
        occupancy = (stat >> 16) & 0xFFFF
        flags = stat & 0xFFFF
        
        # Decode the flags bitmask into a dictionary
        return {
            "occupancy": occupancy,
            "empty":         (flags >> 0) & 0x01,
            "full":          (flags >> 1) & 0x01,
            "almost_empty":  (flags >> 2) & 0x01,
            "almost_full":   (flags >> 3) & 0x01,
            "underflow":     (flags >> 4) & 0x01,
            "overflow":      (flags >> 5) & 0x01
        }
    
    def read_single(self):
        """
        Reads a single 32-bit value from the Input FIFO.

        Returns:
            int: The 32-bit value read.
            None: If the FIFO is empty.
        
        Raises:
            PermissionError: If called on an Output FIFO.
        """
        if self.kind == "out":
            raise PermissionError("Cannot read from an Output FIFO")
        
        # Check if data is available (bit 0 of status is EMPTY)
        status = self.mmio.read(self._addr_stat)
        if status & 0x01: 
            return None
            
        return self.mmio.read(self._addr_val)

    def write_single(self, value):
        """
        Writes a single 32-bit value to the Output FIFO.

        Parameters:
            value (int): The value to write.

        Raises:
            PermissionError: If called on an Input FIFO.
            RuntimeError: If there is not enough free space to write data.
        """
        if self.kind == "in":
            raise PermissionError("Cannot write to an Input FIFO")
            
        # Check if FIFO is full 
        status = self.mmio.read(self._addr_stat)
        if status & 0x02:
            raise RuntimeError("FIFO is full, cannot write value")
            
        self.mmio.write(self._addr_val, int(value))

    def write_bulk(self, data):
        """
        Writes an entire array or list to the Output FIFO.
        
        Parameters:
            data (list/np.array): Collection of values to write.

        Returns:
            int: The number of samples written to the FIFO.

        Raises:
            PermissionError: If called on an Input FIFO.
            ValueError: If the input data size is larger than the total FIFO depth.
            RuntimeError: If there is not enough free space to fit the entire data block.
        """
        if self.kind == "in":
            raise PermissionError("Cannot write to an Input FIFO")

        # Check if the data is physically too large for the hardware
        data_len = len(data)
        if data_len > self.depth:
            raise ValueError(f"Data size ({data_len}) exceeds total FIFO depth ({self.depth}). ")

        # Check if there is enough available space
        status = self.get_status()
        free_space = self.depth - status['occupancy']
        
        if data_len > free_space:
            raise RuntimeError(
                f"FIFO does not have enough free space for this bulk write. "
                f"Requested: {data_len}, Available: {free_space}."
            )

        
        mem_array = self.mmio.array
        idx = self._offset_val
        
        for val in data:
            mem_array[idx] = int(val)
            
        return data_len
    

    def read_bulk(self, count=None):
        """
        Reads multiple values from the Input FIFO and returns them as a NumPy array.

        Parameters:
            count (int, optional): Number of samples to read. 
                                   If None, reads all currently available samples.
                                   If count > available samples, it will be capped 
                                   to the number of available samples.

        Returns:
            np.ndarray: Array of dtype uint32 containing the FIFO data.

        Raises:
            PermissionError: If called on an Output FIFO.
        """
        if self.kind == "out": 
            raise PermissionError("Cannot read from Output FIFO")
        
        status = self.get_status()
        available = status['occupancy']
        
        # Determine how many samples to actually read
        if count is None or count > available: 
            count = available

        if count <= 0: 
            return np.array([], dtype=np.uint32)

        # Access the memory-mapped array directly for the read loop
        mem_array = self.mmio.array 
        idx = self._offset_val
        
        # Read 'count' times from the same FIFO data register
        raw_list = [mem_array[idx] for _ in range(count)]
        
        return np.array(raw_list, dtype=np.uint32)

    def reset(self):
        """
        Resets the FIFO, clearing all data and flags.
        """
        self.mmio.write(self._addr_ctrl, 1)
        time.sleep(0.001)
        self.mmio.write(self._addr_ctrl, 0)

class Dram:
    """
    Interface for Comblock shared DRAM (AXI-Full).

    Parameters:
            awidth (int): Address width (2^awidth = depth).
            mmio (pynq.MMIO): The MMIO object for the AXI-Full interface.
    """
    def __init__(self, awidth, mmio):
        self.mmio = mmio
        self.depth = 2 ** awidth
        # Pre-cache the array 
        self._buf = self.mmio.array 

    def read_bulk(self, base_addr, count):
        """
        Reads a block of data from DRAM using NumPy slicing.

        Parameters:
            base_addr (int): The starting address in DRAM.
            count (int): Number of 32-bit words to read.

        Returns:
            np.ndarray: A copy of the requested memory block.
        """
        end = base_addr + count
        if end > self.depth:
            end = self.depth
        return self._buf[base_addr:end].copy()

    def write_bulk(self, base_addr, data):
        """
        Writes an entire array/list to DRAM using high-speed slice assignment.

        Parameters:
            base_addr (int): The starting address in DRAM.
            data (list/np.array): The data to write.

        Raises:
            IndexError: If the data length exceeds the remaining DRAM depth.
        """
        count = len(data)
        end = base_addr + count
        
        if end > self.depth:
            raise IndexError(f"End address {end} exceeds RAM depth {self.depth}")

        self._buf[base_addr:end] = data

    def write_single(self, addr, value):
        """
        Writes a single 32-bit value to a specific DRAM address.

        Parameters:
            addr (int): The memory address.
            value (int): The value to write.

        Raises:
            IndexError: If the address is out of range.
        """
        if addr >= self.depth:
            raise IndexError(f"Address {addr} out of range")
            
        self._buf[addr] = int(value)
        
    def read_single(self, addr):
        """
        Reads a single 32-bit value from a specific DRAM address.

        Parameters:
            addr (int): The memory address.

        Returns:
            int: The 32-bit value read.

        Raises:
            IndexError: If the address is out of range.
        """
        if addr >= self.depth:
            raise IndexError(f"Address {addr} out of range")
            
        return self._buf[addr]
