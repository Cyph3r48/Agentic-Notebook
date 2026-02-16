param(
    [switch]$NoDeps
)

$argsList = @("compose", "run", "--rm")
if ($NoDeps) {
    $argsList += "--no-deps"
}
$argsList += @("backend", "python", "-m", "pytest", "-q", "tests")

docker @argsList

