import math
from collections.abc import Sequence

from django import forms
from django.core.exceptions import ValidationError


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
