# Comblock_API_for_PYNQ
A high-level Python driver for the ICTP Comblock IP core on PYNQ. This driver simplifies communication between the Zynq Processing System (PS) and Programmable Logic (PL) by providing an easy-to-use API for AXI-Lite registers, FIFOs, and AXI-Full DRAM.

## Features

- **Automatic Binding**: Seamlessly integrates with PYNQ overlays using `DefaultIP`.
- **Safe Register Access**: Boundary-checked read/write operations for Input and Output registers.
- **Smart FIFO Interface**: 
    - Decodes hardware status bitmasks into readable Python dictionary.
    - Supports single-value and high-speed bulk transfers using NumPy.
    - Built-in protection against overflows and underflows.
- **High-Speed DRAM**: Optimized AXI-Full memory access using NumPy slicing.
- **Robust Error Handling**: Descriptive exceptions (`PermissionError`, `IndexError`, `RuntimeError`) to prevent illegal hardware states.

## Hardware Tested

- **Board**: Arty Z7-20 (or any Zynq-7000/Zynq UltraScale+ board running PYNQ).
- **IP Core**: [ICTP Comblock](https://gitlab.com/rodrigomelo9/core-comblock/-/tree/master) (v2.0).
- **Software**: [PYNQ](https://www.pynq.io/) package version v3.0.1 .

## Installation

Simply copy the `comblock.py` file into your Jupyter Notebook directory on your PYNQ board, or clone this repository:

```bash
git clone https://github.com/jcgallego1/Comblock_API_for_PYNQ.git
```

## Quick Start

### 1. Load the Overlay
```python
from pynq import Overlay
from comblock import Comblock

overlay = Overlay("your_bitstream.bit")
# The driver binds automatically if the IP is named 'comblock' in Vivado
cb = overlay.comblock_0 
```

### 2. Simple Registers
```python
# Write to an Output Register
cb.OUT_REGS.write(offset=0, value=123)

# Read from an Input Register
val = cb.IN_REGS.read(offset=0)
print(f"Register Value: {val}")
```

### 3. Using the FIFO
```python
# Check FIFO status (Returns a decoded dictionary)
status = cb.FIFO_IN.get_status()
print(f"Samples available: {status['occupancy']}")

if not status['empty']:
    # Read all available data into a NumPy array
    data = cb.FIFO_IN.read_bulk()
    print(data)
```

### 4. Shared DRAM (AXI-Full)
```python
import numpy as np

# Write a block of data
my_data = np.arange(100, dtype=np.uint32)
cb.DRAM.write_bulk(0, data=my_data)

# Read it back
result = cb.DRAM.read_bulk(0, count=100)
```

## API Reference

### `Register`
- `read(offset)`: Returns the 32-bit value at the specified index.
- `write(offset, value)`: Writes a value to the specified index (Output registers only).

### `Fifo`
- `get_status()`: Returns a dictionary with `occupancy`, `empty`, `full`, `almost_empty`, `almost_full`, `underflow`, and `overflow`.
- `read_bulk(count=None)`: Reads `count` samples (or all available) into a NumPy array.
- `write_bulk(data)`: Writes an array/list to the FIFO. Raises `RuntimeError` if space is insufficient.
- `reset()`: Clears the FIFO.

### `Dram`
- `read_bulk(base_addr, count)`: High-speed block read.
- `write_bulk(base_addr, data)`: High-speed block write.

## License

This project is licensed under the **BSD 3-Clause License** - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Based on the [ICTP Comblock IP](https://gitlab.com/rodrigomelo9/core-comblock/-/tree/master).

