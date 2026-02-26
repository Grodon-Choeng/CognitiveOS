from piccolo.columns import Integer, Varchar

from app.core import BaseModel


class EmbeddingRecord(BaseModel):
    memory_id = Integer(index=True)
    model_name = Varchar(length=64)
    dimension = Integer()
    vector_id = Integer(index=True)

    class Meta:
        tablename = "embedding_record"
