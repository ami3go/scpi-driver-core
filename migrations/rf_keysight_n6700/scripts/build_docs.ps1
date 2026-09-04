. "$PSScriptRoot\_common.ps1"
& $Python -m robot.libdoc KeysightN6700Library docs\KeysightN6700Library.html
& $Python -m mkdocs build --strict --clean
