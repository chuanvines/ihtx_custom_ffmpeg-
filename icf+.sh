#!/usr/bin/env bash

# icf+.sh - IHTX Custom FFmpeg+ for Linux (mirrors icf+.exe)
#
# Usage:
#   ./icf+.sh [--hidelogs] <input> <output> <exports> <dur_frac> <no_trim> <input_format> <output_format> [ffmpeg args...]
#
# Example:
#   ./icf+.sh input.mp4 output.mp4 10 0.4 - mov mp4 \
#     -vf "setpts=0.5*PTS,drawtext=text=$(($i+1)):x='(w-text_w)/2+sin(t13)':y=60+sin(tan(t5))*10:fontsize=w/12:fontcolor=white:bordercolor=black:borderw=6" \
#     -af atempo=2 -c:v ffv1 -c:a pcm_s16le
#
# Notes:
#   - Requires ffmpeg and ffprobe in PATH.
#   - no_trim: true/yes/+ = no trimming, false/no/- = trim to dur_frac.
#   - exports may be negative to reverse the concat order.

hidelogs=0
args=()
for a in "$@"; do
   if [ "$a" = "--hidelogs" ]; then
      hidelogs=1
   else
      args+=("$a")
   fi
done
set -- "${args[@]}"

start=$(date +%s%3N)

if [ "$#" -lt 7 ]; then
   echo "Usage: ./icf+.sh [--hidelogs] <input> <output> <exports> <dur_frac> <no_trim> <input_format> <output_format> [ffmpeg args...]" >&2
   exit 2
fi

FILE="$1"
OUTPUT="$2"
exports="$3"
dur="$4"
no_trim="$5"
input_format="$6"
output_format="$7"
shift 7
ffmpeg_args="$*"

if [ ! -f "$FILE" ]; then
   echo "input file not found: $FILE" >&2
   exit 1
fi

abs_exports=$(awk -v e="$exports" 'BEGIN{ if(e<0) printf e*-1; else printf e }')

if [ "$abs_exports" -lt 1 ]; then
   echo "exports must be non-zero" >&2
   exit 1
fi

if [ "$input_format" = "default" ]; then
   input_format=$(basename "$FILE" | sed 's/.*\.//')
fi
if [ "$output_format" = "default" ]; then
   output_format=$(basename "$FILE" | sed 's/.*\.//')
fi

log=err_$RANDOM.log

die() {
   echo "ERROR: $1" >&2
   if [ "$hidelogs" -eq 0 ]; then
      [ -f "$log" ] && cat "$log" >&2
   fi
   exit 1
}

mkdir -p "$(dirname "$OUTPUT")"

# Build lossless intermediate 0.mov (always trimmed to dur, infinite loop)
if ! ffmpeg -loglevel error -hide_banner -y -stream_loop -1 -i "$FILE" -c:v utvideo -c:a alac -t "$dur" -threads 0 -movflags +faststart 0.mov 2>>"$log"; then
   die "intermediate 0.mov creation failed"
fi
if [ ! -f "0.mov" ]; then
   die "0.mov was not created even though ffmpeg exited 0 (is utvideo supported? check 'ffmpeg -encoders | grep utvideo')"
fi

case "$no_trim" in
   true|yes|+)
      trim=0
      ;;
   false|no|-)
      trim=1
      ;;
   *)
      echo "invalid no_trim: $no_trim (expected true/yes/+ or false/no/-)" >&2
      exit 1
      ;;
esac

# Render each export.
# $ffmpeg_args is intentionally left unquoted: bash performs word-splitting and
# evaluates any $i / $(($i+1)) arithmetic per export (i = current export index).
i=0
if [ "$trim" -eq 0 ]; then
   if ! ffmpeg -loglevel error -hide_banner -y -i "0.mov" $ffmpeg_args -movflags +faststart "1.$input_format" 2>>"$log"; then
      die "render 1 failed: ffmpeg -i 0.mov $ffmpeg_args -movflags +faststart 1.$input_format"
   fi
   for ((i=1; i<=abs_exports; i++)); do
      if ! ffmpeg -loglevel error -hide_banner -y -i "$i.$input_format" $ffmpeg_args -movflags +faststart "$((i+1)).$input_format" 2>>"$log"; then
         die "render $((i+1)) failed: ffmpeg -i $i.$input_format $ffmpeg_args -movflags +faststart $((i+1)).$input_format"
      fi
   done
else
   if ! ffmpeg -loglevel error -hide_banner -y -stream_loop 1 -i "0.mov" $ffmpeg_args -t "$dur" -movflags +faststart "1.$input_format" 2>>"$log"; then
      die "render 1 failed: ffmpeg -stream_loop 1 -i 0.mov $ffmpeg_args -t $dur -movflags +faststart 1.$input_format"
   fi
   for ((i=1; i<=abs_exports; i++)); do
      if ! ffmpeg -loglevel error -hide_banner -y -stream_loop 1 -i "$i.$input_format" $ffmpeg_args -t "$dur" -movflags +faststart "$((i+1)).$input_format" 2>>"$log"; then
         die "render $((i+1)) failed: ffmpeg -stream_loop 1 -i $i.$input_format $ffmpeg_args -t $dur -movflags +faststart $((i+1)).$input_format"
      fi
   done
fi

# Build concat list
> concat.txt
if [ "$exports" -lt 0 ]; then
   for ((n=abs_exports; n>=1; n--)); do
      echo "file '$n.$input_format'" >> concat.txt
   done
else
   for ((n=1; n<=abs_exports; n++)); do
      echo "file '$n.$input_format'" >> concat.txt
   done
fi

# Concat all exports
case "$output_format" in
   mkv)  ffmpeg -loglevel error -hide_banner -y -f concat -safe 0 -i "concat.txt" -c:v mpeg2video -q:v 1 -c:a flac -pix_fmt yuv420p -bufsize 16M -movflags +faststart -threads 0 "$OUTPUT" 2>>"$log";;
   mxf)  ffmpeg -loglevel error -hide_banner -y -f concat -safe 0 -i "concat.txt" -c:v mpeg2video -qscale 1 -qmin 1 -c:a pcm_s16le -ar 48000 -pix_fmt yuv420p -bufsize 16M -movflags +faststart -threads 0 "$OUTPUT" 2>>"$log";;
   mov)  ffmpeg -loglevel error -hide_banner -y -f concat -safe 0 -i "concat.txt" -c:v libx264 -profile:v high -level:v 5 -tune film -q:v 1 -crf 30 -g 9 -bf 0 -preset superfast -c:a aac -b:a 224K -aac_coder fast -pix_fmt yuv420p -bufsize 16M -movflags +faststart -threads 0 "$OUTPUT" 2>>"$log";;
   mp4)  ffmpeg -loglevel error -hide_banner -y -f concat -safe 0 -i "concat.txt" -c:v libx264 -profile:v high -level:v 5 -tune film -q:v 1 -crf 30 -g 9 -bf 0 -preset superfast -c:a aac -b:a 224K -aac_coder fast -pix_fmt yuv420p -bufsize 16M -movflags +faststart -threads 0 "$OUTPUT" 2>>"$log";;
   avi)  ffmpeg -loglevel error -hide_banner -y -f concat -safe 0 -i "concat.txt" -c:v mpeg2video -c:a flac -pix_fmt yuv420p -movflags +faststart "$OUTPUT" 2>>"$log";;
   webm) ffmpeg -loglevel error -hide_banner -y -f concat -safe 0 -i "concat.txt" -pix_fmt yuv420p -movflags +faststart "$OUTPUT" 2>>"$log";;
   *)    ffmpeg -loglevel error -hide_banner -y -f concat -safe 0 -i "concat.txt" -pix_fmt yuv420p -bufsize 16M -movflags +faststart -threads 0 "$OUTPUT" 2>>"$log";;
esac
if [ $? -ne 0 ]; then
   die "concat failed"
fi
if [ ! -f "$OUTPUT" ]; then
   die "output was not created"
fi

file_size=$(stat -c%s "$OUTPUT" 2>/dev/null || echo 0)

if [ "$file_size" -ge 1048576 ]; then
   fs=$(awk -v f="$file_size" 'BEGIN{ printf "%.2f", f/1048576 }')' MB'
else
   fs=$(awk -v f="$file_size" 'BEGIN{ printf "%.2f", f/1024 }')' KB'
fi

end=$(date +%s%3N)

if [ -f "$OUTPUT" ]; then
   echo "Done: $OUTPUT ($fs, took $(awk -v start="$start" -v end="$end" 'BEGIN{ printf "%.3f", (end-start)/1000 }') seconds)"
else
   [ "$hidelogs" -eq 0 ] && cat "$log" >&2
   exit 1
fi

# Cleanup
rm -f concat.txt 0.mov 0.mp4
for ((n=1; n<=abs_exports+1; n++)); do
   rm -f "$n.$input_format"
done
rm -f "$log"
