import pytest
import torch
from pytorch_lightning import seed_everything
from transformers import BertTokenizer

from transformers_lightning.language_modeling.masked_language_modeling import IGNORE_IDX, MaskedLanguageModeling
from transformers_lightning.language_modeling.utils import whole_word_tails_mask

tok = BertTokenizer.from_pretrained('bert-base-cased')
mlm = MaskedLanguageModeling(tok, whole_word_masking=True)


@pytest.mark.parametrize(
    ["seed", "sentence", "masking"], [
        [0, "how are you man?", [IGNORE_IDX, IGNORE_IDX, 1132, 1128, IGNORE_IDX, IGNORE_IDX, IGNORE_IDX]],
        [
            1, "The quick brown fox jumps over the lazy dog",
            [
                IGNORE_IDX, IGNORE_IDX, IGNORE_IDX, IGNORE_IDX, 17594, IGNORE_IDX, IGNORE_IDX, IGNORE_IDX, IGNORE_IDX,
                IGNORE_IDX, IGNORE_IDX
            ]
        ],
        [
            8, "Be or not to be a superstar",
            [
                IGNORE_IDX, IGNORE_IDX, IGNORE_IDX, IGNORE_IDX, IGNORE_IDX, IGNORE_IDX, IGNORE_IDX, 7688, 10058,
                IGNORE_IDX
            ]
        ], [3, "", [IGNORE_IDX, IGNORE_IDX]],
        [
            4, "share silence or say what you think?",
            [IGNORE_IDX, IGNORE_IDX, 3747, IGNORE_IDX, 1474, 1184, IGNORE_IDX, IGNORE_IDX, IGNORE_IDX, IGNORE_IDX]
        ]
    ]
)
def test_language_model(seed, sentence, masking):

    seed_everything(seed)

    input_ids = torch.tensor([tok.encode(sentence)])
    words_tails_mask = whole_word_tails_mask(input_ids, tok)

    original = input_ids.clone()

    masked, labels = mlm(input_ids, words_tails=words_tails_mask)

    assert torch.all(torch.where(labels != IGNORE_IDX, labels, masked).eq(original))

    labels = labels.tolist()[0]
    assert labels == masking, f"{labels} different from {masking}"
