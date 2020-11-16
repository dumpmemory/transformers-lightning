from torch.utils.data import Dataset
from transformers_lightning.datasets import SuperTransformersDataset


class TransformersMapDataset(SuperTransformersDataset, Dataset):
    """
    Superclass of all map datasets. Tokenization is performed on the fly.
    Dataset is split in chunks to save memory using the relative dataframe function.
    """
    def __init__(self, *args):
        super().__init__(*args)
        self.data = list(iter(self.adapter))

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx) -> dict:
        """ Get dict of data at a given position. """
        if idx < 0:
            if -idx > len(self):
                raise ValueError("absolute value of index should not exceed dataset length")
            idx = len(self) + idx

        assert 0 <= idx < len(self), (
            f"Received index out of range {idx}, range: {0} <= idx < {len(self)}"
        )

        row = self.data[idx]
        row_dict = self.adapter.preprocess_line(row)

        return row_dict
