# -*- coding: utf-8 -*-
""" Optimize subcommands for HLSCLT.

Copyright (c) 2018 Víctor Mayoral Vilches
"""

### Imports ###
import click
import shutil
import os
from ..build_commands import build_commands
from hlsclt.helper_funcs import find_solution_num
import subprocess
from glob import glob

###################################################
### Supporting Functions###
###################################################
# Callback function used to exit the program on a negative user prompt response
def abort_if_false(ctx, param, value):
    if not value:
        ctx.abort()

def build_tcl_file(ctx, clk_target):
    config = ctx.obj.config
    solution_num = ctx.obj.solution_num
    try:
        file = click.open_file("run_hls.tcl","w")
        file.write("open_project " + config["project_name"] + "\n")
        file.write("set_top " + config["top_level_function_name"] + "\n")
        if config.get("cflags","") != "":
            cf = " -cflags \"%s\"" % config["cflags"]
        else:
            cf = ""
        for src_file in config["src_files"]:
            file.write("add_files " + config["src_dir_name"] + "/" + src_file + cf + "\n")
        for tb_file in config["tb_files"]:
            file.write("add_files -tb " + config["tb_dir_name"] + "/" + tb_file + "\n")
        # generate new solution
        file.write("open_solution -reset \"solution" + str(solution_num) + "\"" + "\n")
        file.write("set_part " + config["part_name"] + "\n")
        file.write("create_clock -period " + str(clk_target) + " -name default" + "\n")
        return file
    except OSError:
        click.echo("Woah! Couldn't create a Tcl run file in the current folder!")
        raise click.Abort()

# Funtion to remove generated files
def optimize_results_clock(ctx):
        """ Automatically generate results iterating over different clock periods

        TODO: allow for user selected ranges
        """
        # Define the clock targets (in ns) that will be used to optimize latency and resources
        # optimize_clock_targets = [5, 10]
        optimize_clock_targets = [5, 6, 7, 8, 9, 10, 11]

        config = ctx.obj.config
        # no keep flag,iterate manually
        ctx.obj.solution_num = find_solution_num(ctx) + 1
        # Iterate over the different clock targets
        click.secho("Optimizing current HLS design", bold=True)
        # Iterate over each one of the targets
        for clk_target in optimize_clock_targets:
            click.echo(click.style("Optimizing for clock=" + str(clk_target)+" ns @ solution" + str(ctx.obj.solution_num), fg='yellow'))
            # Setup the file
            ctx.obj.file = build_tcl_file(ctx, clk_target)
            # Add the syn step
            ctx.obj.file.write("csynth_design" + "\n")
            ctx.obj.file.write("exit" + "\n")
            ctx.obj.file.close()
            # Call the Vivado HLS process
            returncode = subprocess.call(["vivado_hls -f run_hls.tcl"],shell=True)
            # Check return status of the HLS process.
            if returncode < 0:
                raise click.Abort()
            elif returncode > 0:
                click.echo("Warning: HLS Process returned an error, skipping report opening!")
                raise click.Abort()
            else:
                pass

            # Iterate over the solution number for the next loop iterations
            ctx.obj.solution_num +=1

def display_optimize(ctx):
    """ Process existing solutions and display them """
    config = ctx.obj.config
    # Seach for solution folders
    paths = glob(config["project_name"] + "/solution*/")

    # Create data structures to hold the results.
    #  each element in the dictionary contains:
    #     "solutionN": [clk_estimated, float(clk_estimated)*float(interval_max),
    #                        ,bram_utilization, dsp_utilization, ff_utilization, lut_utilization]
    results = {}

    for path in paths:
        try:
            solution_key = path.split("/")[1] # e.g. solution1
            with click.open_file(path + "/syn/report/" + config["top_level_function_name"] + "_csynth.rpt","r") as f:
                results_from_solution = []
                # Information is typically assembled as follows in this report:
                #
                # 14 ...
                # 15 ================================================================
                # 16 == Performance Estimates
                # 17 ================================================================
                # 18 + Timing (ns):
                # 19     * Summary:
                # 20     +--------+-------+----------+------------+
                # 21     |  Clock | Target| Estimated| Uncertainty|
                # 22     +--------+-------+----------+------------+
                # 23     |ap_clk  |   5.00|     3.492|        0.62|
                # 24     +--------+-------+----------+------------+
                # 25
                # 26 + Latency (clock cycles):
                # 27     * Summary:
                # 28     +-----+-----+-----+-----+---------+
                # 29     |  Latency  |  Interval | Pipeline|
                # 30     | min | max | min | max |   Type  |
                # 31     +-----+-----+-----+-----+---------+
                # 32     |  686|  686|  686|  686|   none  |
                # 33     +-----+-----+-----+-----+---------+
                # 34 ...
                # 44 ================================================================
                # 45 == Utilization Estimates
                # 46 ================================================================
                # 47 * Summary:
                # 48 +-----------------+---------+-------+--------+-------+
                # 49 |       Name      | BRAM_18K| DSP48E|   FF   |  LUT  |
                # 50 +-----------------+---------+-------+--------+-------+
                # 51 |DSP              |        -|      -|       -|      -|
                # 52 |Expression       |        -|      -|       0|     39|
                # 53 |FIFO             |        -|      -|       -|      -|
                # 54 |Instance         |        -|      -|       -|      -|
                # 55 |Memory           |        -|      -|       -|      -|
                # 56 |Multiplexer      |        -|      -|       -|      -|
                # 57 |Register         |        -|      -|       -|      -|
                # 58 +-----------------+---------+-------+--------+-------+
                # 59 |Total            |        0|      0|       0|     39|
                # 60 +-----------------+---------+-------+--------+-------+
                # 61 |Available        |      280|    220|  106400|  53200|
                # 62 +-----------------+---------+-------+--------+-------+
                # 63 |Utilization (%)  |        0|      0|       0|   ~0  |
                # 64 +-----------------+---------+-------+--------+-------+
                # 65 ...

                # Fetch line 23:
                #       |ap_clk  |   5.00|     3.492|        0.62|
                report_content = f.readlines()
                ap_clk_line = report_content[22]
                ap_clk_line_elements = [x.strip() for x in ap_clk_line.split('|')]
                clk_target = ap_clk_line_elements[2]
                clk_estimated = ap_clk_line_elements[3]
                clk_uncertainty = ap_clk_line_elements[4]
                results_from_solution.append(clk_target)
                results_from_solution.append(clk_estimated)

                # Fetch line 32, latency in cycles
                #       |  686|  686|  686|  686|   none  |
                summary_line = report_content[31]
                summary_line_elements = [x.strip() for x in summary_line.split('|')]
                latency_min = summary_line_elements[1]
                latency_max = summary_line_elements[2]
                interval_min = float(summary_line_elements[3]) + 1
                interval_max = float(summary_line_elements[4]) + 1
                results_from_solution.append((float(clk_estimated) + float(clk_uncertainty))*float(interval_max))

                # Fetch line 32, latency in cycles
                #       |Utilization (%)  |        0|      0|       0|   ~0  |
                # By default it's line 63
                utilization_line = report_content[62]
                total_line = report_content[58]
                # this line may not always be in the same positon thereby we need to search for it
                # and rewrite it
                for i in range(len(report_content)):
                    if "Utilization" in report_content[i]:
                        utilization_line = report_content[i]
                        total_line = report_content[i - 4]

                utilization_line_elements = [x.strip() for x in utilization_line.split('|')]
                bram_utilization = utilization_line_elements[2]
                dsp_utilization = utilization_line_elements[3]
                ff_utilization = utilization_line_elements[4]
                lut_utilization = utilization_line_elements[5]

                total_line_elements = [x.strip() for x in total_line.split('|')]
                bram_total = total_line_elements[2]
                dsp_total = total_line_elements[3]
                ff_total = total_line_elements[4]
                lut_total = total_line_elements[5]

                results_from_solution.append(bram_total)
                results_from_solution.append(bram_utilization)
                results_from_solution.append(dsp_total)
                results_from_solution.append(dsp_utilization)
                results_from_solution.append(ff_total)
                results_from_solution.append(ff_utilization)
                results_from_solution.append(lut_total)
                results_from_solution.append(lut_utilization)

                # append results from this iteration in the general dictionary
                results[solution_key] = results_from_solution

            f.close()
        except IOError:
            pass
        except IndexError:
            continue

    # Create data structures to hold the results.
    #  each element in the dictionary contains:
    #     "solutionN": [clk_target, clk_estimated, float(clk_estimated)*float(interval_max),
    #                        ,bram_total, bram_utilization, dsp_total, dsp_utilization,
    #                         ff_total, ff_utilization, lut_total, lut_utilization]
    click.echo("Solution#" + "\t" + "tar.clk" + "\t" + "est.clk" + "\t\t" + "time_max" + "\t"+"BRAM_18K"
        + "\t"+ "DSP48E"+ "\t"+ "FF"+ "\t"+ "LUT")

    # Order dict according to time, (element[2])
    results = sorted(results.items(), key=lambda x: x[1][2])

    # Print results
    # for key, element in results.items():
    for key, element in results:
        click.echo(str(key) + "\t" + click.style(str(element[0]), fg="yellow") + "\t" + str(element[1])
            + "\t\t" + click.style(str(element[2]), fg="cyan") + "\t\t" + str(element[3]) + " (" + str(element[4])
            + "%)\t\t" + str(element[5]) + " (" + str(element[6]) + "%)\t" + str(element[7]) + " (" + str(element[8])
            + "%)\t" + str(element[9]) + " (" + str(element[10]) + "%)\t")

###################################################

### Click Command Definitions ###
# Optimize Command
@click.command('optimize', short_help='Automatically find the best compromise between resources and timing constraints.')
@click.option('-g', '--generate', is_flag=True, help='Generate new solutions for the optimization.')
# @click.option('--yes', is_flag=True, callback=abort_if_false,
#               expose_value=False,
#               prompt='Are you sure you want to remove all generated files?',
#               help='Force quiet removal.')
@click.pass_context
def optimize(ctx, generate):
    """Automatically find the best compromise between resources and timing constraints."""
    if generate:
        optimize_results_clock(ctx)
        display_optimize(ctx)
    else:
        display_optimize(ctx)
