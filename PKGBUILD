# Maintainer: Hyper Hu <hypersoweak@gmail.com>
pkgname=tapstats-git
pkgver=r13.a06f2b6
pkgrel=1
pkgdesc="Keyboard and mouse input statistics for Wayland with Waybar integration"
arch=("x86_64")
url="https://github.com/HyperSoWeak/tapstats"
license=("MIT")
depends=("python" "python-evdev" "python-textual")
makedepends=("git" "python-build" "python-installer" "python-wheel" "python-hatchling")
install=tapstats.install
source=("_build::git+$url.git")
sha256sums=("SKIP")

pkgver() {
  cd _build
  printf "r%s.%s" "$(git rev-list --count HEAD)" "$(git rev-parse --short HEAD)"
}

build() {
  cd _build
  python -m build --wheel --no-isolation
}

package() {
  cd _build
  python -m installer --destdir="$pkgdir" dist/*.whl
  install -Dm644 systemd/tapstats.service \
    "$pkgdir/usr/lib/systemd/user/tapstats.service"
  install -Dm644 tapstats.install \
    "$pkgdir/usr/share/tapstats/tapstats.install"
}
