# Runs the real project-level synth_1 (and optionally impl_1) run, once all
# individual modules have synthesized cleanly out-of-context. This is what
# produces the authoritative, whole-design timing numbers.
#
# Usage: vivado -mode batch -source synth_full.tcl -tclargs <project.xpr> <output_dir> <synth_only|impl>

if {[llength $argv] < 3} {
    puts "ERROR: usage: synth_full.tcl <project.xpr> <output_dir> <synth_only|impl>"
    exit 1
}

set xpr_path [lindex $argv 0]
set out_dir  [lindex $argv 1]
set do_impl  [lindex $argv 2]

if {[catch {open_project $xpr_path} err]} {
    puts "FULL_SYNTH_ERROR: failed to open project: $err"
    exit 1
}

puts "FULL_SYNTH_START"

reset_run synth_1
launch_runs synth_1 -jobs 4
wait_on_run synth_1

set synth_status [get_property STATUS [get_runs synth_1]]
if {[string match "*ERROR*" $synth_status] || [string match "*FAILED*" $synth_status]} {
    puts "FULL_SYNTH_ERROR: $synth_status"
    close_project
    exit 1
}

open_run synth_1
report_timing_summary -file [file join $out_dir "full_synth_timing.rpt"] -max_paths 10
report_utilization -file [file join $out_dir "full_synth_utilization.rpt"]
puts "FULL_SYNTH_OK"

if {$do_impl eq "impl"} {
    puts "FULL_IMPL_START"
    reset_run impl_1
    launch_runs impl_1 -to_step route_design -jobs 4
    wait_on_run impl_1

    set impl_status [get_property STATUS [get_runs impl_1]]
    if {[string match "*ERROR*" $impl_status] || [string match "*FAILED*" $impl_status]} {
        puts "FULL_IMPL_ERROR: $impl_status"
        close_project
        exit 1
    }

    open_run impl_1
    report_timing_summary -file [file join $out_dir "full_impl_timing.rpt"] -max_paths 10
    report_utilization -file [file join $out_dir "full_impl_utilization.rpt"]
    puts "FULL_IMPL_OK"
}

close_project

