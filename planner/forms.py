import math
from collections.abc import Sequence

from django import forms
from django.core.exceptions import ValidationError


PRODUCTION_UPGRADE_CHOICES = tuple(
    (f"{percentage / 100:g}", f"{percentage}% increase")
    for percentage in range(0, 201, 25)
)
FUEL_UPGRADE_CHOICES = tuple(
    (f"{percentage / 100:g}", f"{percentage}% reduction")
    for percentage in range(0, 201, 25)
)


class PlanRequestForm(forms.Form):
    target = forms.CharField(
        label="Target material",
        widget=forms.TextInput(
            attrs={
                "list": "target-materials",
                "autocomplete": "off",
                "placeholder": "Search materials",
            }
        ),
    )
    rate = forms.FloatField(
        label="Rate per second",
        widget=forms.TextInput(
            attrs={"inputmode": "decimal", "placeholder": "e.g. 2"}
        ),
    )
    item_rate_upgrade = forms.ChoiceField(
        label="Item production (and consumption) rate increase",
        choices=PRODUCTION_UPGRADE_CHOICES,
        initial="0",
    )
    fuel_consumption_upgrade = forms.ChoiceField(
        label="Fuel consumption reduction",
        choices=FUEL_UPGRADE_CHOICES,
        initial="0",
    )
    active_tab = forms.CharField(
        required=False,
        widget=forms.HiddenInput,
        initial="standard",
    )

    def __init__(
        self, *args: object, materials: Sequence[str], **kwargs: object
    ) -> None:
        super().__init__(*args, **kwargs)
        self.materials = frozenset(materials)

    def clean_target(self) -> str:
        target = self.cleaned_data["target"]
        if target not in self.materials:
            raise ValidationError("Choose a material from the suggestions.")
        return target

    def clean_rate(self) -> float:
        rate = self.cleaned_data["rate"]
        if not math.isfinite(rate) or rate <= 0:
            raise ValidationError("Enter a finite rate greater than zero.")
        return rate

    def clean_active_tab(self) -> str:
        active_tab = self.cleaned_data["active_tab"] or "standard"
        if active_tab not in {"standard", "upgrades"}:
            raise ValidationError("Choose a valid planner tab.")
        return active_tab
