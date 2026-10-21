import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from core.models import Campus, User  # noqa: E402
from core.testing import grant  # noqa: E402
from students.models import Course, Enrollment, Student  # noqa: E402


def ensure_user(username, password, *permissions):
    user, _ = User.objects.get_or_create(username=username)
    user.set_password(password)
    user.is_active = True
    user.save()
    grant(user, *permissions)
    return user


def main():
    password = os.environ["E2E_PASSWORD"]
    campus, _ = Campus.objects.get_or_create(name="Campus E2E CI", defaults={"active": True})
    campus.active = True
    campus.save(update_fields=["active"])

    manager = ensure_user("e2e-manager", password, "manage_calls", "assign_calls")
    manager.campuses.add(campus)
    caller = ensure_user("e2e-caller", password, "manage_calls")
    caller.campuses.add(campus)

    course, _ = Course.objects.get_or_create(
        campus=campus,
        name="CURSO E2E",
        schedule="LUNES",
        group="1",
    )
    student, _ = Student.objects.get_or_create(
        campus=campus,
        full_name="ESTUDIANTE E2E",
        defaults={"phone": "999999999"},
    )
    Enrollment.objects.get_or_create(campus=campus, student=student, course=course)
    print("Datos ficticios E2E creados.")


if __name__ == "__main__":
    main()
