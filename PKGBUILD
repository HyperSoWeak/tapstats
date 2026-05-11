# Maintainer: your name <your@email.com>
pkgname=tapstats-git
pkgver=r1.0000000
pkgrel=1
pkgdesc="Keyboard and mouse input statistics for Wayland with Waybar integration"
arch=("x86_64")
url="https://github.com/USERNAME/tapstats"
license=("MIT")
depends=("python" "python-evdev" "python-textual")
makedepends=("git" "python-build" "python-installer" "python-wheel" "python-hatchling")
install=tapstats.install
source=("tapstats::git+file://$startdir")
# Before publishing to AUR, change to:
# source=("tapstats::git+$url.git")
sha256sums=("SKIP")

pkgver() {
    cd tapstats
    printf "r%s.%s" "$(git rev-list --count HEAD)" "$(git rev-parse --short HEAD)"
}

build() {
    cd tapstats
    python -m build --wheel --no-isolation
}

package() {
    cd tapstats
    python -m installer --destdir="$pkgdir" dist/*.whl
    install -Dm644 systemd/tapstats.service \
        "$pkgdir/usr/lib/systemd/user/tapstats.service"
    install -Dm644 tapstats.install \
        "$pkgdir/usr/share/tapstats/tapstats.install"
}
