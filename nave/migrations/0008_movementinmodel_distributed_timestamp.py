# Generated by Django 5.1.4 on 2024-12-22 17:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nave', '0007_movementindistributionmodel_timestamp_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='movementinmodel',
            name='distributed_timestamp',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
