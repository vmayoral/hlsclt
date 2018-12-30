# -*- coding: utf-8 -*-
""" Optimize subcommands for HLSCLT.

Copyright (c) 2018 Víctor Mayoral Vilches
"""

### Imports ###
import click
import shutil
import os
from ..build_commands import build_commands

### Supporting Functions###
# Callback function used to exit the program on a negative user prompt response
def abort_if_false(ctx, param, value):
    if not value:
        ctx.abort()

# Funtion to remove generated files
def optimize_results(ctx):
        config = ctx.obj.config
        click.echo("Main function.")
        build_commands.build(ctx)

### Click Command Definitions ###
# Optimize Command
@click.command('optimize',short_help='Automatically find the best compromise between resources and timing constraints.')
# @click.option('--yes', is_flag=True, callback=abort_if_false,
#               expose_value=False,
#               prompt='Are you sure you want to remove all generated files?',
#               help='Force quiet removal.')
@click.pass_context
def optimize(ctx):
    """Automatically find the best compromise between resources and timing constraints."""
    optimize_results(ctx)
