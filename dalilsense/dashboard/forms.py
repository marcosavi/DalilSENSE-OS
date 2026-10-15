"""Validated experiment settings; no changes to global narrator defaults."""
import random
import re

from django import forms

from dalilsense.narrator import DECODING, DEFAULT_MODEL, SYSTEM_PROMPT


def model_choices(models):
    def size(model):
        match = re.fullmatch(r"([\d.]+)\s*([BM])", model.get("details", {}).get("parameter_size", ""), re.I)
        return float(match[1]) * (1 if match[2].upper() == "B" else .001) if match else float("inf")

    choices = []
    for model in sorted(models, key=lambda m: (size(m), m["name"])):
        details = model.get("details", {})
        info = [model["name"].split(":")[0]]
        if details.get("parameter_size"):
            info.append(details["parameter_size"])
        if details.get("quantization_level"):
            info.append(details["quantization_level"])
        if size(model) <= 3:
            info.append("Small model")
        choices.append((model["name"], " · ".join(info)))
    return choices


class ExperimentForm(forms.Form):
    name = forms.CharField(label="Run name", max_length=120, required=False,
                           widget=forms.TextInput(attrs={"placeholder": "e.g., Small model, guided prompt"}))
    model = forms.ChoiceField(label="Ollama model")
    system_prompt = forms.CharField(label="System prompt", max_length=20000, strip=False,
                                    widget=forms.Textarea(attrs={"rows": 10}), initial=SYSTEM_PROMPT.strip())
    selection = forms.ChoiceField(label="Choose inputs", initial="first", choices=[
        ("first", "First N cases (sorted by filename)"),
        ("random", "Random sample with a fixed seed"),
        ("manual", "Select specific cases"),
    ])
    case_count = forms.IntegerField(label="Number of JSON files", min_value=1, required=False)
    sample_seed = forms.IntegerField(label="Sampling seed", min_value=0, max_value=2147483647,
                                     initial=42, required=False, help_text="Controls which input cases are sampled.")
    case_ids = forms.MultipleChoiceField(label="Specific cases", required=False,
                                         widget=forms.CheckboxSelectMultiple)
    temperature = forms.FloatField(label="Temperature", min_value=0, max_value=2, initial=DECODING["temperature"],
                                    widget=forms.NumberInput(attrs={"step": "0.1"}), help_text="0–2. Lower values favor less varied outputs.")
    num_predict = forms.IntegerField(label="Maximum output tokens (num_predict)", min_value=1, max_value=16384,
                                     initial=DECODING["num_predict"])
    num_ctx = forms.IntegerField(label="Context window (num_ctx)", min_value=128, max_value=131072,
                                 initial=DECODING["num_ctx"], help_text="Larger windows require more memory; support depends on the model.")
    seed = forms.IntegerField(label="Generation seed", required=False, min_value=0, max_value=2147483647,
                              initial=42, help_text="Helps repeat a run. Identical results across hardware or versions are not guaranteed.")
    top_p = forms.FloatField(label="Top-p", required=False, min_value=0.001, max_value=1,
                             widget=forms.NumberInput(attrs={"step": "0.01"}))
    top_k = forms.IntegerField(label="Top-k", required=False, min_value=0, max_value=1000)
    repeat_penalty = forms.FloatField(label="Repetition penalty", required=False, min_value=0, max_value=2,
                                      widget=forms.NumberInput(attrs={"step": "0.1"}))

    def __init__(self, *args, models, cases, **kwargs):
        super().__init__(*args, **kwargs)
        self.models = {model["name"]: model for model in models}
        self.cases = dict(cases)
        self.fields["model"].choices = model_choices(models)
        choices = self.fields["model"].choices
        self.fields["model"].initial = DEFAULT_MODEL if DEFAULT_MODEL in self.models else choices[0][0] if choices else ""
        self.fields["case_ids"].choices = [(key, key) for key in self.cases]
        self.fields["case_count"].initial = len(cases)
        self.fields["case_count"].max_value = len(cases)
        self.fields["case_count"].widget.attrs["max"] = len(cases)
        for name in ("name", "system_prompt", "sample_seed", "temperature", "num_ctx", "seed"):
            self.fields[name].widget.attrs["aria-describedby"] = f"id_{name}_helptext"

    def clean_system_prompt(self):
        value = self.cleaned_data["system_prompt"]
        if not value.strip():
            raise forms.ValidationError("Enter a system prompt.")
        return value

    def clean(self):
        data = super().clean()
        if not self.cases:
            raise forms.ValidationError("No dataset cases are available.")
        if data.get("selection") == "manual":
            if not data.get("case_ids"):
                self.add_error("case_ids", "Select at least one case.")
        else:
            count = data.get("case_count")
            if count is None or count > len(self.cases):
                self.add_error("case_count", f"Choose between 1 and {len(self.cases)} cases.")
            if data.get("selection") == "random" and data.get("sample_seed") is None:
                self.add_error("sample_seed", "Enter a sampling seed.")
        return data

    def configuration(self):
        data = self.cleaned_data
        ids = sorted(self.cases)
        if data["selection"] == "manual":
            ids = sorted(data["case_ids"])
        elif data["selection"] == "random":
            ids = sorted(random.Random(data["sample_seed"]).sample(ids, data["case_count"]))
        else:
            ids = ids[:data["case_count"]]
        options = {key: data[key] for key in ("temperature", "num_predict", "num_ctx", "seed", "top_p", "top_k", "repeat_penalty")
                   if data.get(key) is not None}
        model = self.models[data["model"]]
        return {
            "name": data["name"] or data["model"], "model": data["model"],
            "model_digest": model.get("digest", ""), "model_details": model.get("details", {}),
            "system_prompt": data["system_prompt"], "options": options, "think": False,
            "selection": data["selection"],
            "sample_seed": data["sample_seed"] if data["selection"] == "random" else None,
            "cases": [{"case_id": key, "input": self.cases[key]} for key in ids],
        }
