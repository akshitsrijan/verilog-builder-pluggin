# Dumps the project's compile order (leaf modules first) to a text report.
# The Python orchestrator parses this file; keep this script mechanical.
#
# Usage: vivado -mode batch -source get_hierarchy.tcl -tclargs <project.xpr> <output_dir>

if {[llength $argv] < 2} {
    puts "ERROR: usage: get_hierarchy.tcl <project.xpr> <output_dir>"
    exit 1
}

set xpr_path [lindex $argv 0]
set out_dir  [lindex $argv 1]

if {[catch {open_project $xpr_path} err]} {
    puts "HIERARCHY_ERROR: failed to open project: $err"
    exit 1
}

if {[catch {
    report_compile_order -of_objects [get_filesets sources_1] -file [file join $out_dir "compile_order.rpt"]
} err]} {
    puts "HIERARCHY_ERROR: report_compile_order failed: $err"
    close_project
    exit 1
}

close_project
puts "HIERARCHY_OK"

