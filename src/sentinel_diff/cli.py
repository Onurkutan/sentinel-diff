"""
Command-line interface for sentinel-diff.
"""

import click
from sentinel_diff import __version__


@click.group()
@click.version_option(version=__version__)
def main():
    """sentinel-diff: Multi-temporal satellite change detection from open Sentinel-2 data."""
    pass


@main.command()
def status():
    """Show pipeline status and environment configuration."""
    click.echo(f"sentinel-diff v{__version__} - Environment ready.")


if __name__ == "__main__":
    main()
