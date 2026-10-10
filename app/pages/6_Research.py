"""Preserved methodology landing page."""
import pathlib
import runpy

runpy.run_path(str(pathlib.Path(__file__).resolve().parents[1] / "research_home.py"), run_name="__main__")
