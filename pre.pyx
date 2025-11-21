$namespace default
!define pi:
    3.14159

!macro circle_area(r):
    print(r * r * pi)
$

$namespace util
!macro pr(x):
    print("DEBUG:", x)
$