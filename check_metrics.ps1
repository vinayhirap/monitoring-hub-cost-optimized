$r = Invoke-RestMethod -Uri 'http://13.127.154.112/api/v1/label/__name__/values'
foreach ($x in $r.data) {
    if ($x -like '*ec2*') { Write-Host $x }
}