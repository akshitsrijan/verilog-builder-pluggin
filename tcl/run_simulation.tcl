# Runs a behavioral (functional) simulation of a testbench and logs every
# signal transition to a waveform database, so /generate_waveform can show
# it in the Vivado GUI afterward. Works identically for combinational or
# sequential designs - it's the testbench driving stimulus that differs,
# not this script.
#
# Usage: vivado -mode batch -source run_simulation.tcl \
#          -tclargs <project.xpr> <tb_file_or_empty> <tb_top> <sim_time> <output_dir>

if {[llength $argv] < 5} {
    puts "ERROR: usage: run_simulation.tcl <project.xpr> <tb_file> <tb_top> <sim_time> <output_dir>"
    exit 1
}

set xpr_path [lindex $argv 0]
set tb_file  [lindex $argv 1]
set tb_top   [lindex $argv 2]
set sim_time [lindex $argv 3]
set out_dir  [lindex $argv 4]

if {[catch {open_project $xpr_path} err]} {
    puts "WAVEFORM_ERROR: failed to open project: $err"
    exit 1
}

puts "WAVEFORM_START: $tb_top"

if {[llength [get_filesets -quiet sim_1]] == 0} {
    create_fileset -simset sim_1
}

if {$tb_file ne ""} {
    if {[catch {add_files -fileset sim_1 -norecurse $tb_file} err]} {
        puts "WAVEFORM_ERROR: failed to add testbench: $err"
        close_project
        exit 1
    }
}

if {$tb_top ne ""} {
    if {[catch {
        set_property top $tb_top [get_filesets sim_1]
        set_property top_lib xil_defaultlib [get_filesets sim_1]
    } err]} {
        puts "WAVEFORM_ERROR: failed to set sim top: $err"
        close_project
        exit 1
    }
}

update_compile_order -fileset sim_1

if {[catch {launch_simulation} err]} {
    puts "WAVEFORM_ERROR: launch_simulation failed: $err"
    catch {close_project}
    exit 1
}

# log_wave marks signals to actually be written to the waveform database -
# without this, the simulation still runs but nothing gets recorded.
if {[catch {log_wave -recursive *} err]} {
    puts "WAVEFORM_ERROR: log_wave failed: $err"
    catch {close_sim}
    catch {close_project}
    exit 1
}

set sim_dir [get_property DIRECTORY [current_sim]]

if {[catch {run $sim_time} err]} {
    puts "WAVEFORM_ERROR: run failed: $err"
    catch {close_sim}
    catch {close_project}
    exit 1
}

catch {write_wave_config -force [file join $out_dir "waveform.wcfg"]}

puts "SIM_DIR: $sim_dir"

close_sim
close_project
puts "WAVEFORM_OK: $tb_top"
