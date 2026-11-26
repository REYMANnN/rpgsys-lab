# alvo 1 GHz em ASAP7 (unidade: ps)
create_clock -name clk -period 1000 [get_ports clk]
set_input_delay 100 -clock clk [delete_from_list [all_inputs] [get_ports clk]]
set_output_delay 100 -clock clk [all_outputs]
