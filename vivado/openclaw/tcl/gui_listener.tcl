# Runs inside a persistent Vivado GUI process for the duration of a build.
# Opens a local TCP socket (localhost only) and waits for one-line commands
# from the Python orchestrator, so the same GUI window can be pointed at a
# new module's checkpoint (or the final project run) as the build
# progresses, instead of a new window opening/closing per step.
#
# Protocol: client connects, sends one line, gets one line back, connection
# closes. Commands:
#   PING                        -> PONG
#   MODULE <name> <dcp_path>    -> opens that module's out-of-context
#                                   checkpoint and tries to show its schematic
#   FULL <run_name>             -> opens the real project and that run
#                                   (synth_1 / impl_1) and tries to show its
#                                   schematic
#   WAVE <wdb_path>             -> opens a waveform database in the
#                                   waveform viewer
#   QUIT                        -> closes the socket and exits Vivado
#
# Usage: vivado -mode gui -source gui_listener.tcl -tclargs <port> <project_xpr>

if {[llength $argv] < 2} {
    puts "GUI_LISTENER_ERROR: usage: gui_listener.tcl <port> <project_xpr>"
    exit 1
}

set listen_port     [lindex $argv 0]
set g_project_xpr   [lindex $argv 1]
set g_project_opened 0

proc dispatch {line} {
    global g_project_xpr g_project_opened

    set parts [split $line " "]
    set cmd [lindex $parts 0]

    if {$cmd eq "PING"} {
        return "PONG"
    }

    if {$cmd eq "MODULE"} {
        set name [lindex $parts 1]
        set dcp  [lindex $parts 2]
        if {![file exists $dcp]} {
            return "ERROR: checkpoint not found: $dcp"
        }
        catch {close_design}
        if {[catch {open_checkpoint $dcp} err]} {
            return "ERROR: open_checkpoint failed: $err"
        }
        catch {show_schematic [get_cells -hier -filter {PRIMITIVE_LEVEL==LEAF}]}
        return "OK: showing module $name"
    }

    if {$cmd eq "FULL"} {
        set run_name [lindex $parts 1]
        catch {close_design}
        if {!$g_project_opened} {
            if {[catch {open_project $g_project_xpr} err]} {
                return "ERROR: open_project failed: $err"
            }
            set g_project_opened 1
        }
        if {[catch {open_run $run_name} err]} {
            return "ERROR: open_run failed: $err"
        }
        catch {show_schematic [get_cells -hier -filter {PRIMITIVE_LEVEL==LEAF}]}
        return "OK: showing $run_name"
    }

    if {$cmd eq "WAVE"} {
        set wdb [lindex $parts 1]
        if {![file exists $wdb]} {
            return "ERROR: waveform db not found: $wdb"
        }
        if {[catch {open_wave_database $wdb} err]} {
            return "ERROR: open_wave_database failed: $err"
        }
        return "OK: showing waveform $wdb"
    }

    if {$cmd eq "QUIT"} {
        after 200 {exit 0}
        return "OK: closing"
    }

    return "ERROR: unknown command: $cmd"
}

proc handle_conn {sock addr port} {
    fconfigure $sock -buffering line -blocking 1
    if {[catch {gets $sock line} n] || $n < 0} {
        catch {close $sock}
        return
    }
    set reply [dispatch $line]
    catch {puts $sock $reply}
    catch {close $sock}
}

socket -server handle_conn -myaddr 127.0.0.1 $listen_port
puts "GUI_LISTENER_READY: port=$listen_port"

