param(
    [string]$Example = "01_simulator_smoke.robot",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RobotArguments
)
. "$PSScriptRoot\_common.ps1"
$ExamplePath = Join-Path $RepoRoot "examples\robot\$Example"
if (-not (Test-Path $ExamplePath)) {
    throw "Example not found: $ExamplePath"
}
& $Python -m robot --outputdir "build\example-results\$([IO.Path]::GetFileNameWithoutExtension($Example))" @RobotArguments $ExamplePath
