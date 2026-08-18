# Synthesizes a single module out-of-context so it can be built and reported
# on independently of the rest of the hierarchy (sub-instances are treated
# as black boxes). This is what gives us module-by-module progress instead
# of one opaque top-level synthesis run.
#
# Usage: vivado -mode batch -source synth_module.tcl -tclargs <project.xpr> <module_name> <output_dir>

if {[llength $argv] < 3} {
    puts "ERROR: usage: synth_module.tcl <project.xpr> <module_name> <output_dir>"
    exit 1
}

set xpr_path [lindex $argv 0]
set module   [lindex $argv 1]
set out_dir  [lindex $argv 2]

if {[catch {open_project $xpr_path} err]} {
    puts "MODULE_SYNTH_ERROR: failed to open project: $err"
    exit 1
}

puts "MODULE_SYNTH_START: $module"

if {[catch {
    synth_design -top $module -mode out_of_context
} err]} {
    puts "MODULE_SYNTH_ERROR: $err"
    close_project
    exit 1
}

catch {write_checkpoint -force [file join $out_dir "${module}_synth.dcp"]}
catch {report_timing_summary -file [file join $out_dir "${module}_timing.rpt"] -max_paths 10}
catch {report_utilization -file [file join $out_dir "${module}_utilization.rpt"]}

close_project
puts "MODULE_SYNTH_OK: $module"

