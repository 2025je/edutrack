from django.db import migrations, models
import django.db.models.deletion


def copy_legacy_promoters(apps, schema_editor):
    Enrollment = apps.get_model("students", "Enrollment")
    EnrollmentPromoter = Enrollment.promoter.through
    database = schema_editor.connection.alias
    assignments = (
        Enrollment.objects.using(database)
        .exclude(legacy_promoter_id__isnull=True)
        .values_list("pk", "legacy_promoter_id")
        .iterator()
    )
    EnrollmentPromoter.objects.using(database).bulk_create(
        EnrollmentPromoter(enrollment_id=enrollment_id, promoter_id=promoter_id)
        for enrollment_id, promoter_id in assignments
    )


def restore_legacy_promoters(apps, schema_editor):
    Enrollment = apps.get_model("students", "Enrollment")
    EnrollmentPromoter = Enrollment.promoter.through
    database = schema_editor.connection.alias
    for enrollment_id in Enrollment.objects.using(database).values_list("pk", flat=True).iterator():
        promoter_id = (
            EnrollmentPromoter.objects.using(database)
            .filter(enrollment_id=enrollment_id)
            .order_by("promoter_id")
            .values_list("promoter_id", flat=True)
            .first()
        )
        if promoter_id is not None:
            Enrollment.objects.using(database).filter(pk=enrollment_id).update(
                legacy_promoter_id=promoter_id
            )


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0007_enrollment_enrollment_date"),
    ]

    operations = [
        migrations.RenameField(
            model_name="enrollment",
            old_name="promoter",
            new_name="legacy_promoter",
        ),
        migrations.AlterField(
            model_name="enrollment",
            name="legacy_promoter",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="legacy_enrollments",
                to="students.promoter",
                verbose_name="Promotor histórico",
            ),
        ),
        migrations.AddField(
            model_name="enrollment",
            name="promoter",
            field=models.ManyToManyField(
                blank=True,
                related_name="enrollments",
                to="students.promoter",
                verbose_name="Promotores",
            ),
        ),
        migrations.RunPython(copy_legacy_promoters, restore_legacy_promoters),
        migrations.RemoveField(
            model_name="enrollment",
            name="legacy_promoter",
        ),
    ]
