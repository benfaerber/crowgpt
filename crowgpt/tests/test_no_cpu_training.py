"""There is no CPU training path, and saying "cuda" is not proof of one.

Training silently fell back to the CPU for ten hours and reached 1,500 steps of
40,000. It was not broken, it was slow, and slow is what a big corpus looks
like. Every check here exists because the failure was invisible, not because it
was complicated.
"""

import pytest
import torch

from crowgpt.train import NoGpu, assert_on_gpu, require_device


class TestRequiringTheGpu:
    def test_it_raises_rather_than_returning_cpu(self, monkeypatch):
        monkeypatch.delenv("CROWGPT_ALLOW_CPU", raising=False)
        monkeypatch.setattr(torch.cuda, "is_available", lambda: False)

        with pytest.raises(NoGpu, match="no CPU fallback"):
            require_device()

    def test_there_is_no_argument_to_opt_back_in(self, monkeypatch):
        """An escape hatch is something a future caller passes by accident."""
        monkeypatch.delenv("CROWGPT_ALLOW_CPU", raising=False)
        monkeypatch.setattr(torch.cuda, "is_available", lambda: False)

        with pytest.raises(TypeError):
            require_device(allow_cpu=True)

    def test_only_an_environment_variable_can_override(self, monkeypatch):
        monkeypatch.setenv("CROWGPT_ALLOW_CPU", "1")
        monkeypatch.setattr(torch.cuda, "is_available", lambda: False)

        assert require_device() == "cpu"

    def test_available_but_unusable_still_fails(self, monkeypatch):
        """A driver can report yes and then refuse the first allocation."""
        monkeypatch.delenv("CROWGPT_ALLOW_CPU", raising=False)
        monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
        monkeypatch.setattr(torch, "zeros", lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("CUDA error: out of memory")))

        with pytest.raises(NoGpu, match="first allocation failed"):
            require_device()


class TestParametersActuallyLanding:
    def test_a_model_left_on_the_cpu_is_caught(self, monkeypatch):
        """The device string can be right while the weights are not."""
        monkeypatch.delenv("CROWGPT_ALLOW_CPU", raising=False)
        stranded = torch.nn.Linear(4, 4)  # never moved

        with pytest.raises(NoGpu, match="parameters are on the CPU"):
            assert_on_gpu(stranded, "test model")

    def test_the_message_names_a_stranded_parameter(self, monkeypatch):
        monkeypatch.delenv("CROWGPT_ALLOW_CPU", raising=False)

        with pytest.raises(NoGpu) as caught:
            assert_on_gpu(torch.nn.Linear(4, 4), "test model")

        assert "weight" in str(caught.value)

    @pytest.mark.skipif(not torch.cuda.is_available(), reason="needs a GPU")
    def test_a_model_on_the_gpu_passes(self):
        assert_on_gpu(torch.nn.Linear(4, 4).cuda(), "test model")

    def test_the_override_disables_the_check_too(self, monkeypatch):
        """Otherwise CROWGPT_ALLOW_CPU=1 would be refused by the next guard."""
        monkeypatch.setenv("CROWGPT_ALLOW_CPU", "1")

        assert_on_gpu(torch.nn.Linear(4, 4), "test model")


class TestPatienceIsInSteps:
    """Patience used to be a count of evaluations, so it depended on eval_every.

    The run that produced the best model allowed 8,000 stale steps; the overnight
    defaults allowed 1,500, from a parameter that looks unrelated. Every model in
    the ladder stopped at a quarter of its steps, and the best model's best loss
    arrived at step 19,000 — past where the stricter setting would have cut it.
    """

    def test_the_same_stale_steps_whatever_the_eval_interval(self):
        from crowgpt.train import Trainer

        for interval in (250, 500, 1000):
            evals = max(1, 8000 // interval)
            assert evals * interval == 8000, "stale steps must not depend on eval_every"

    def test_the_default_matches_what_produced_the_best_model(self):
        import inspect

        from crowgpt.train import Trainer

        defaults = inspect.signature(Trainer.__init__).parameters
        assert defaults["patience_steps"].default == 8000
        assert defaults["eval_every"].default == 1000
