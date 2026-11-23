#!/usr/bin/env bash
# Cut a recorded check video into time-stamped contact sheets (CLAUDE.md "You are the eyes": read motion as frames).
#   bash frames.sh <video.webm> [fps=8] [from_s=0] [to_s=end]
# Writes <video dir>/sheets/s01.jpg... - 16 frames each (4 x 4), the video time on every frame.
set -euo pipefail
v="$1"; fps="${2:-8}"; from="${3:-0}"; to="${4:-}"
out="$(dirname "$v")/sheets"
rm -rf "$out"; mkdir -p "$out"
range=(-ss "$from"); [ -n "$to" ] && range+=(-to "$to")
ffmpeg -v error -y "${range[@]}" -i "$v" -vf "setpts=PTS+${from}/TB,fps=${fps},scale=480:-1,drawtext=fontfile='C\:/Windows/Fonts/arial.ttf':text='%{pts\:hms}':x=6:y=6:fontsize=18:fontcolor=yellow:box=1:boxcolor=black@0.6,tile=4x4" -q:v 4 "$out/s%02d.jpg"
ls "$out" | wc -l
