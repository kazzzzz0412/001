#!/bin/sh
# Install the heavy Japanese gothic the image tools letter with.
#
# Without it they fall back to IPAGothic and thicken it themselves, which is
# legible but lighter than a real Black weight. Debian/Ubuntu only; on other
# systems install Noto Sans CJK (Bold or Black) however that system does it,
# or pass any heavy font with --font.
set -e

if [ -f /usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc ]; then
    echo "Noto Sans CJK Black is already installed"
    exit 0
fi

SUDO=""
[ "$(id -u)" -eq 0 ] || SUDO="sudo"

$SUDO apt-get update
$SUDO apt-get install -y --no-install-recommends fonts-noto-cjk fonts-noto-cjk-extra
echo "installed: $(fc-list :lang=ja family style | grep -c Black) black faces"
