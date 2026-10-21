import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def populate_campuses(apps, schema_editor):
    members = apps.get_model("calls", "CallListMember")
    call_lists = apps.get_model("calls", "CallList")
    database = schema_editor.connection.alias
    for call_list in call_lists.objects.using(database).all().iterator():
        members.objects.using(database).filter(call_list_id=call_list.pk).update(
            campus_id=call_list.campus_id
        )


class Migration(migrations.Migration):
    dependencies = [
        ("calls", "0013_whatsapp_send"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="calllistmember",
            name="campus",
            field=models.ForeignKey(
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="core.campus",
                verbose_name="Sede",
            ),
        ),
        migrations.RunPython(populate_campuses, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="calllistmember",
            name="campus",
            field=models.ForeignKey(
                editable=False,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="core.campus",
                verbose_name="Sede",
            ),
        ),
        migrations.AlterField(
            model_name="calllistmember",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="call_memberships",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Usuario",
            ),
        ),
        migrations.AddConstraint(
            model_name="calllistmember",
            constraint=models.UniqueConstraint(
                fields=("user", "campus"), name="unique_call_member_campus"
            ),
        ),
    ]
