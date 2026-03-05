"""Tests for HyDE: hypothetical document embeddings."""
from alaya.index.hyde import generate_hypothetical_document


class TestGenerateHypotheticalDocument:
    def test_what_is_question(self):
        doc = generate_hypothetical_document("what is kubernetes?")
        assert "kubernetes" in doc.lower()
        assert len(doc) > len("what is kubernetes?")

    def test_how_to_question(self):
        doc = generate_hypothetical_document("how to deploy with argocd?")
        assert "argocd" in doc.lower()
        assert "deploy" in doc.lower()

    def test_why_question(self):
        doc = generate_hypothetical_document("why use helm charts?")
        assert "helm" in doc.lower()

    def test_plain_query(self):
        doc = generate_hypothetical_document("kubernetes deployment strategy")
        assert "kubernetes" in doc.lower()
        assert "deployment" in doc.lower()

    def test_output_is_longer_than_input(self):
        query = "kubernetes"
        doc = generate_hypothetical_document(query)
        assert len(doc) > len(query) * 3

    def test_strips_question_mark(self):
        doc = generate_hypothetical_document("what are helm charts?")
        # The topic extraction should work cleanly
        assert "helm charts" in doc.lower()

    def test_empty_query(self):
        doc = generate_hypothetical_document("")
        assert isinstance(doc, str)
