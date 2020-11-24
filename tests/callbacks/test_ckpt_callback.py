import multiprocessing
from argparse import Namespace
import os
from transformers_lightning.callbacks.transformers_model_checkpoint import TransformersModelCheckpointCallback
from transformers_lightning.datamodules import SuperDataModule

from transformers import BertTokenizer
import shutil

import pytest
import pytorch_lightning as pl
from tests.datamodule.test_utils import SimpleTransformerLikeModel, ExampleAdapter

n_cpus = multiprocessing.cpu_count()


class ExampleDataModule(SuperDataModule):

    def __init__(self, *args, test_number=1, tokenizer=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.train_adapter = ExampleAdapter(self.hparams, f"test{test_number}.tsv", delimiter="\t", tokenizer=tokenizer)
        self.valid_adapter = ExampleAdapter(self.hparams, f"test{test_number}.tsv", delimiter="\t", tokenizer=tokenizer)
        self.test_adapter = [ExampleAdapter(self.hparams, f"test{test_number}.tsv", delimiter="\t", tokenizer=tokenizer) for _ in range(2)]


# Test iter dataset work correctly
@pytest.mark.parametrize(
    ["epochs", "accumulate_grad_batches", "batch_size", "callback_interval", "val_callback", "expected_results"], [
    [2,         3,                         4,            3,                   False,         ["hparams.json",
                                                                                              "ckpt_epoch_0_step_3",
                                                                                              "ckpt_epoch_0_step_6",
                                                                                              "ckpt_epoch_0_step_8",
                                                                                              "ckpt_epoch_1_step_9",
                                                                                              "ckpt_epoch_1_step_12",
                                                                                              "ckpt_epoch_1_step_15",
                                                                                              "ckpt_epoch_1_step_16_final"]],
    [1,         2,                         5,            6,                   False,         ["hparams.json",
                                                                                              "ckpt_epoch_0_step_6",
                                                                                              "ckpt_epoch_0_step_10_final"]],
    [1,         2,                         5,            6,                   True,          ["hparams.json",
                                                                                              "ckpt_epoch_0_step_1",
                                                                                              "ckpt_epoch_0_step_3",
                                                                                              "ckpt_epoch_0_step_5",
                                                                                              "ckpt_epoch_0_step_6",
                                                                                              "ckpt_epoch_0_step_8",
                                                                                              "ckpt_epoch_0_step_10_final"]],
])
def test_datamodule_cpu(epochs, accumulate_grad_batches, batch_size, callback_interval, val_callback, expected_results):

    os.environ["CUDA_VISIBLE_DEVICES"] = ""

    hparams = Namespace(
        batch_size=batch_size,
        val_batch_size=batch_size,
        test_batch_size=batch_size,
        accumulate_grad_batches=accumulate_grad_batches,
        num_workers=4,
        dataset_dir='tests/test_data',
        config_dir='tests/test_data',
        cache_dir='cache',
        max_epochs=epochs,
        max_steps=None,
        max_sequence_length=10,
        gpus=0,
        iterable_datasets=False,
        skip_in_training=None,
        checkpoint_interval=callback_interval,
        no_val_checkpointing=not val_callback,
        output_dir="tests/output",
        pre_trained_dir='pre_trained_name',
        name="test",
        val_check_interval=0.25
    )

    tokenizer = BertTokenizer.from_pretrained("bert-base-cased", cache_dir=hparams.cache_dir)

    callback = TransformersModelCheckpointCallback(hparams)

    # instantiate PL trainer
    trainer = pl.Trainer.from_argparse_args(
        hparams,
        profiler='simple',
        logger=None,
        callbacks=[callback],
    )

    # instantiate PL model
    model = SimpleTransformerLikeModel(hparams)    

    # Datasets
    datamodule = ExampleDataModule(hparams, test_number=2, tokenizer=tokenizer)

    model.datamodule = datamodule
    trainer.fit(model, datamodule=datamodule)

    folder = os.path.join(hparams.output_dir, hparams.pre_trained_dir, hparams.name)
    listing = os.listdir(folder)
    shutil.rmtree(hparams.output_dir)
    assert set(listing) == set(expected_results), f"{listing} vs {set(expected_results)}"

    

