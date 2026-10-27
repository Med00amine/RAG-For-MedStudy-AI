import numpy as np
import pytest

from app.embeddings.embedder import get_embedder


@pytest.mark.slow
def test_similar_texts_are_closer():
    embedder = get_embedder()
    cat, kitten, car = np.array(
        embedder.embed_documents(
            ["A cat sleeps on the sofa", "A kitten naps on the couch", "Engine oil change"]
        )
    )

    assert cat.shape == (embedder.model.get_sentence_embedding_dimension(),)
    assert cat @ kitten > cat @ car
