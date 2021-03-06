#! /bin/sh
set -e

if [ ! -f "athena_version.py" ] ; then
    echo "Warning: didn't find athena_version.py, so running build_preflight.py first"
    python ./build_preflight.py
fi
VERSION=`python athena_version.py`

pyinstaller ./src/main.py --add-data "ui:ui" --add-data "tools:tools" --add-data "sample_inputs:sample_inputs" \
                          --add-data "src/qml:qml" --add-data "src/shaders:shaders" --add-data "src/txt:txt" \
                          --add-data "athena_version.py:." \
                          --add-binary "${VIRTUAL_ENV}/lib/python3.7/site-packages/PySide2/Qt/plugins/geometryloaders:qt5_plugins/geometryloaders" \
                          --osx-bundle-identifier="edu.mit.lcbb.athena" \
                          --name Athena --icon "icon/athena.icns" --windowed $*
plutil -insert NSHighResolutionCapable -bool true dist/Athena.app/Contents/Info.plist
plutil -replace CFBundleShortVersionString -string ${VERSION} dist/Athena.app/Contents/Info.plist
