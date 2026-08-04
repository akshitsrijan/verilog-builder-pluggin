---
description: Create a brand-new Vivado project by prompting - write RTL or point at existing files, no manual Vivado GUI steps
argument-hint: "[optional: project name and/or design description]"
---

Create a new Vivado project end-to-end from a prompt, using the verilog-builder MCP tools.
This is the counterpart to `/verilog-build`: that command only works on a project that
already exists on disk; this one creates the `.xpr` in the first place.

Arguments: `$ARGUMENTS` (optional project name and/or a description of the design)

1. **Figure out the source of the RTL.** Ask the user (unless `$ARGUMENTS` already makes it
   obvious) whether they want to:
   - describe a design and have you write the Verilog for it, or
   - point you at existing `.v`/`.sv` file(s) already on disk to wrap in a new project.
   Either is fine - `create_project` just needs a list of source file paths that exist on
   disk by the time it's called.

2. **Resolve project name and location.** If not given, ask for a project name. Default
   `project_dir` to `~/<project_name>/` unless the user wants somewhere else - this matches
   every existing project on this machine (`two_one_mux/`, `VIO/`, `FSM/`, etc.).

3. **If writing new RTL:** write the Verilog module(s) with the Write tool under
   `<project_dir>/sources/` (create the directory), using sensible module/file naming. Show
   the user the RTL before proceeding so they can request changes - don't create the Vivado
   project around code they haven't seen.

4. **If wrapping existing files:** confirm the resolved absolute path(s) exist and ask which
   one is the top module if it's not obvious from the file/module names.

5. **Ask about constraints and target part** only if relevant (e.g. the design uses I/O that
   needs pin assignments). Otherwise skip constraints entirely and default `part` to
   `xc7a35tcpg236-1` (Basys3, matching the other projects here) - don't ask about the part
   number unless the user has a reason to want something else.

6. **Call `create_project`** with `project_name`, `source_files` (absolute paths), and
   `project_dir`, plus `constraints_file`/`top`/`part` if applicable. If it returns an
   `error`, show it plainly (common cause: a project already exists at that path) and stop -
   don't retry blindly.

7. **On success**, tell the user the new `.xpr` path, then ask if they want to kick off a
   build right away. If yes, proceed exactly like `/verilog-build` from its step 2 onward
   (ask synth vs full, default `gui=true`, stream live progress). If not, mention they can
   run `/verilog-build <project_name>` whenever they're ready.
