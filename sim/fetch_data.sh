#!/bin/sh
# Fetch the simulation's ground truth: Çatalhöyük East Mound, Buildings 1 and 5
# (matrix by Craig Cessford), from T. S. Dye's hm examples at a pinned commit,
# and verify it. GPL-3.0 upstream, so it is fetched rather than vendored.
#   sh sim/fetch_data.sh [target-dir]      (default: sim/data/catalhoyuk-bldg-1-5)
set -eu
COMMIT=9229fa7dfbfbfe23035ccfda8d89345d750e003f
BASE=https://raw.githubusercontent.com/tsdye/harris-matrix/$COMMIT/examples/bldg-1-5
DEST=${1:-sim/data/catalhoyuk-bldg-1-5}
mkdir -p "$DEST"
for f in bldg-1-5-contexts.csv bldg-1-5-observations.csv bldg-1-5-periods.csv bldg-1-5-dates.csv bldg-1-5-plain.ini; do
  curl -fsSL -o "$DEST/$f" "$BASE/$f"
done
cd "$DEST"
sha256sum -c <<'SUMS'
49f8f2cb666d758890fa01bd32d01e05fb31782ef726eca95f2c599d4a126405  bldg-1-5-contexts.csv
0e9ceff3c7a85a7501259229d0656bfab3a6f2cb03f4f60c391d897dcf9cab1c  bldg-1-5-observations.csv
b3902ecfe1f67680019dd90b807f8649d36b435a4158fc1e9492e213ee7c20b0  bldg-1-5-periods.csv
422c7ade6c03bbfb4ed192babd23bd872ed6313f265dddc38e941149dbbc6b8d  bldg-1-5-dates.csv
4dd94b8ee2c349d51a95c56a29105695fb8c85692a329c9c4bccb779acaa34c1  bldg-1-5-plain.ini
SUMS
