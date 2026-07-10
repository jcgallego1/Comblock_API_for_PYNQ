----------------------------------------------------------------------------------
-- Company: 
-- Engineer: 
-- 
-- Create Date: 05/10/2026 11:02:35 AM
-- Design Name: 
-- Module Name: fifo_odd_generator_v2 - Behavioral
-- Project Name: 
-- Target Devices: 
-- Tool Versions: 
-- Description: 
-- 
-- Dependencies: 
-- 
-- Revision:
-- Revision 0.01 - File Created
-- Additional Comments:
-- 
----------------------------------------------------------------------------------

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity fifo_odd_generator is
    generic (
        DATA_WIDTH     : integer := 16;   
        TOTAL_DATA     : integer := 1024; 
        MAX_COUNT_BITS : integer := 12 
    );
    port (
        clk_i          : in  std_logic; -- 300 MHz
        axil_aclk      : in  std_logic; -- 100 MHz
        rst_i          : in  std_logic; 
        start_i        : in  std_logic_vector(31 downto 0); 
        done_o         : out std_logic_vector(31 downto 0);
        freq_meter_o   : out std_logic_vector(31 downto 0);
        fifo_full_i    : in  std_logic;                     
        fifo_we_o      : out std_logic;                     
        fifo_data_o    : out std_logic_vector(DATA_WIDTH - 1 downto 0)  
    );
end fifo_odd_generator;

architecture rtl of fifo_odd_generator is

    -- Sincronización CDC
    signal start_sync : std_logic_vector(2 downto 0) := (others => '0');
    signal start_f    : std_logic;

    -- Registros de Pipeline (Para romper caminos largos)
    signal counter          : unsigned(MAX_COUNT_BITS - 1 downto 0) := (others => '0');
    signal is_last_sample   : std_logic := '0';
    signal fifo_full_reg    : std_logic := '0';
    
    -- Máquina de estados simple
    type state_t is (IDLE, RUNNING, DONE_ST);
    signal state : state_t := IDLE;

    -- Salidas registradas (Crucial para Timing)
    signal we_r    : std_logic := '0';
    signal data_r  : std_logic_vector(DATA_WIDTH - 1 downto 0) := (others => '0');
    signal done_r  : std_logic := '0';

    -- Medidor de frecuencia
    signal cyc_cnt : unsigned(31 downto 0) := (others => '0');
    signal cyc_sync : std_logic_vector(31 downto 0) := (others => '0');

begin

    -- 1. Sincronizar Start (100MHz -> 300MHz)
    process(clk_i) begin
        if rising_edge(clk_i) then
            start_sync <= start_sync(1 downto 0) & start_i(0);
        end if;
    end process;
    start_f <= start_sync(2);

    -- 2. Pipeline de señales de control
    -- Registramos 'full' para que el camino desde el ComBlock no sea tan largo
    process(clk_i) begin
        if rising_edge(clk_i) then
            fifo_full_reg <= fifo_full_i;
            -- Pre-calculamos si el siguiente es el último para evitar comparadores lentos
            if counter = to_unsigned(TOTAL_DATA - 2, MAX_COUNT_BITS) then
                is_last_sample <= '1';
            else
                is_last_sample <= '0';
            end if;
        end if;
    end process;

    -- 3. Lógica Principal (FSM segmentada)
    process(clk_i)
    begin
        if rising_edge(clk_i) then
            if rst_i = '0' then
                state   <= IDLE;
                counter <= (others => '0');
                we_r    <= '0';
                done_r  <= '0';
            else
                we_r <= '0'; -- Default

                case state is
                    when IDLE =>
                        done_r  <= '0';
                        counter <= (others => '0');
                        if start_f = '1' then
                            state <= RUNNING;
                        end if;

                    when RUNNING =>
                        -- Usamos el registro de 'full' para mejorar timing
                        -- Nota: Esto puede causar que escribamos 1 dato extra si no tenemos cuidado,
                        -- pero el ComBlock suele ignorar WE si está lleno.
                        if fifo_full_reg = '0' then
                            we_r   <= '1';
                            -- Cálculo impar ultra-rápido (solo cables)
                            data_r <= std_logic_vector(resize(counter, DATA_WIDTH-1) & '1');
                            
                            if is_last_sample = '1' then
                                state <= DONE_ST;
                            else
                                counter <= counter + 1;
                            end if;
                        end if;

                    when DONE_ST =>
                        done_r <= '1';
                        if start_f = '0' then
                            state <= IDLE;
                        end if;
                end case;
            end if;
        end if;
    end process;

    -- Salidas directas de registros
    fifo_we_o   <= we_r;
    fifo_data_o <= data_r;
    done_o      <= (0 => done_r, others => '0');

    -- Medidor de frecuencia (Sincronizado)
    process(clk_i) begin
        if rising_edge(clk_i) then cyc_cnt <= cyc_cnt + 1; end if;
    end process;
    process(axil_aclk) begin
        if rising_edge(axil_aclk) then cyc_sync <= std_logic_vector(cyc_cnt); end if;
    end process;
    freq_meter_o <= cyc_sync;

end rtl;