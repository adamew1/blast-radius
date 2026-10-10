# Blast Radius — launch the dashboard (Windows). Cache-first, so it works offline from data/raw/.
# Strict offline (fail if a response isn't cached): set $env:BLAST_RADIUS_OFFLINE = "1" before running.
& "$PSScriptRoot\.venv\Scripts\streamlit.exe" run "$PSScriptRoot\app\Home.py"
