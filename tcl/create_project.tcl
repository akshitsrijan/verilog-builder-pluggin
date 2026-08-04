# Creates a brand-new Vivado project from scratch (no manual File > New
# Project needed): adds Verilog/SystemVerilog sources and optional
# constraints, sets the top module, and leaves the project in the same shape
# get_hierarchy.tcl / synth_module.tcl / synth_full.tcl already expect - so
# it drops straight into the module-by-module build flow.
#
# Usage: vivado -mode batch -source create_project.tcl \
#            -tclargs <project_name> <project_dir> <part> <manifest_file>
#
# manifest_file is a plain text file, one entry per line:
#   SRC <path/to/file.v>           (repeatable, at least one required)
#   XDC <path/to/constraints.xdc>  (optional, at most one)
#   TOP <module_name>              (optional; Vivado infers it if omitted)

if {[llength $argv] < 4} {
    puts "CREATE_PROJECT_ERROR: usage: create_project.tcl <project_name> <project_dir> <part> <manifest_file>"
    exit 1
}

set proj_name [lindex $argv 0]
set proj_dir  [lindex $argv 1]
set part      [lindex $argv 2]
set manifest  [lindex $argv 3]

if {![file exists $manifest]} {
    puts "CREATE_PROJECT_ERROR: manifest not found: $manifest"
    exit 1
}

set src_files {}
set xdc_files {}
set top ""

set f [open $manifest r]
while {[gets $f line] >= 0} {
    set line [string trim $line]
    if {$line eq ""} { continue }
    set kind [lindex $line 0]
    set rest [string trim [string range $line [string length $kind] end]]
    if {$kind eq "SRC"} {
        lappend src_files $rest
    } elseif {$kind eq "XDC"} {
        lappend xdc_files $rest
    } elseif {$kind eq "TOP"} {
        set top $rest
    }
}
close $f

if {[llength $src_files] == 0} {
    puts "CREATE_PROJECT_ERROR: no SRC entries in manifest"
    exit 1
}

if {[catch {
    create_project $proj_name $proj_dir -part $part -force
} err]} {
    puts "CREATE_PROJECT_ERROR: create_project failed: $err"
    exit 1
}

if {[catch {
    add_files -norecurse $src_files
} err]} {
    puts "CREATE_PROJECT_ERROR: add_files failed: $err"
    close_project
    exit 1
}

if {[llength $xdc_files] > 0} {
    if {[catch {
        add_files -fileset constrs_1 -norecurse $xdc_files
    } err]} {
        puts "CREATE_PROJECT_ERROR: adding constraints failed: $err"
        close_project
        exit 1
    }
}

if {$top ne ""} {
    catch {set_property top $top [current_fileset]}
}

update_compile_order -fileset sources_1

close_project
puts "CREATE_PROJECT_OK: [file join $proj_dir ${proj_name}.xpr]"
