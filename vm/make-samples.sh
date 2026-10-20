#!/bin/bash
# Regenerates the sample files that land in /home/purr on a fresh image.
# Needs ffmpeg and python3 on the host. The results are committed in vm/samples,
# so this only has to run when a sample changes.
#
#   vm/make-samples.sh [path/to/cabin.png]
set -euo pipefail

HERE=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
S=$HERE/samples
mkdir -p "$S"/{Documents,Downloads,Music,Pictures,Videos}

if [ $# -ge 1 ]; then
    cp "$1" "$S/Pictures/cabin-in-snow.png"
fi

cat > "$S/notes.txt" <<'EOF'
call mom sunday
fix the porch light
try the new ramen place
EOF

cat > "$S/grocery-list.txt" <<'EOF'
milk
eggs
bread
cat food
coffee
apples
EOF

# Tiny one-page PDF, written by hand so no PDF library is needed.
python3 - "$S/Documents/taxes-2025.pdf" <<'PY'
import sys
lines = [
    ("F1", 28, 72, 700, "Taxes 2025 (sample)"),
    ("F2", 13, 72, 660, "This is a sample file that ships with PurrOS."),
    ("F2", 13, 72, 640, "Nothing in here is real. Delete it whenever you like."),
]
ops = []
for font, size, x, y, text in lines:
    t = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    ops.append(f"BT /{font} {size} Tf {x} {y} Td ({t}) Tj ET")
stream = "\n".join(ops).encode()
objs = [
    b"<< /Type /Catalog /Pages 2 0 R >>",
    b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
    b"/Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>",
    b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
]
out = bytearray(b"%PDF-1.4\n")
offsets = []
for i, body in enumerate(objs, 1):
    offsets.append(len(out))
    out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
xref = len(out)
out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
for off in offsets:
    out += b"%010d 00000 n \n" % off
out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
open(sys.argv[1], "wb").write(out)
PY

# 20 s sunset over water: gradient sky that darkens, a sun that sinks below the
# horizon, and a rippling reflection. Soft brown-noise waves for sound.
D=20
ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i "color=c=black:s=2x400:r=30:d=$D" \
  -f lavfi -i "color=c=black@0:s=240x240:r=30:d=$D" \
  -f lavfi -i "color=c=black:s=2x320:r=30:d=$D" \
  -f lavfi -i "anoisesrc=color=brown:amplitude=0.6:sample_rate=44100:duration=$D" \
  -filter_complex "
    [0:v]format=rgb24,geq=
      r='lerp(lerp(46,14,T/$D), lerp(255,170,T/$D), pow(Y/H,1.7))':
      g='lerp(lerp(34,10,T/$D), lerp(150,62,T/$D), pow(Y/H,1.7))':
      b='lerp(lerp(96,40,T/$D), lerp(80,70,T/$D), pow(Y/H,1.7))',
      scale=1280:400:flags=bilinear,format=rgba[sky];
    [1:v]format=rgba,geq=
      r='255':
      g='if(lt(hypot(X-120,Y-120),50),222,165)':
      b='if(lt(hypot(X-120,Y-120),50),150,85)':
      a='if(lt(hypot(X-120,Y-120),50),255,170*exp(-(hypot(X-120,Y-120)-50)/16))'[sun];
    [sky][sun]overlay=x=(W-w)/2:y='60+t*16.5':eval=frame:format=auto,format=gbrp,split[s1][s2];
    [s2]vflip,crop=1280:320:0:0,colorchannelmixer=rr=0.72:gg=0.6:bb=0.68,format=gbrp[wat];
    [2:v]format=gray,geq=lum='128+(2+Y/22)*sin(Y*0.85-T*5.5)',scale=1280:320:flags=neighbor,format=gbrp[xm];
    [2:v]format=gray,geq=lum='128+(1+Y/80)*sin(Y*0.5+T*3)',scale=1280:320:flags=neighbor,format=gbrp[ym];
    [wat][xm][ym]displace=edge=smear[water];
    [s1][water]vstack,setsar=1,format=yuv420p,fade=t=in:st=0:d=0.6,fade=t=out:st=$((D-1)):d=1[v];
    [3:a]lowpass=f=500,tremolo=f=0.15:d=0.8,volume=0.7,afade=t=in:d=1.5,afade=t=out:st=$((D-2)):d=2[a]
  " \
  -map "[v]" -map "[a]" -c:v libx264 -preset slow -crf 24 -profile:v high -pix_fmt yuv420p \
  -c:a aac -b:a 96k -movflags +faststart -t $D "$S/Videos/beach-sunset.mp4"

# 25 s music box loop: C, Am, F, G arpeggios with a soft pluck envelope.
ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i "aevalsrc=exprs='
    st(0, mod(floor(t/0.4), 32));
    st(1, floor(ld(0)/8));
    st(2, mod(ld(0), 8));
    st(3, if(eq(ld(1),0), 0, if(eq(ld(1),1), -3, if(eq(ld(1),2), -7, -5))));
    st(4, if(eq(ld(1),1), 3, 4));
    st(5, if(eq(ld(2),0),0, if(eq(ld(2),1),ld(4), if(eq(ld(2),2),7, if(eq(ld(2),3),12, if(eq(ld(2),4),12+ld(4), if(eq(ld(2),5),12, if(eq(ld(2),6),7, ld(4)))))))));
    st(6, 523.25*pow(2, (ld(3)+ld(5))/12));
    st(7, t - 0.4*floor(t/0.4));
    0.28*exp(-5*ld(7))*(sin(2*PI*ld(6)*t) + 0.3*sin(4*PI*ld(6)*t))
  ':s=44100:d=25.6" \
  -af "aecho=0.8:0.6:180:0.25,afade=t=out:st=23.6:d=2" \
  -c:a libmp3lame -q:a 6 "$S/Music/music-box.mp3"

ls -la "$S" "$S"/*/
