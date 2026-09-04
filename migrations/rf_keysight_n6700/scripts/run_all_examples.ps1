param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RobotArguments
)
. "$PSScriptRoot\_common.ps1"
& $Python -m robot --outputdir build\example-results @RobotArguments examples\robot
