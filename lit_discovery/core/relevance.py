"""Abstract reconstruction, XML cleaning, and query relevance scoring."""
import html
import re

def reconstruct_inverted_abstract(inverted_index):
    """Reconstructs full text from OpenAlex inverted index."""
    if not inverted_index or not isinstance(inverted_index, dict):
        return None
    try:
        word_pos = []
        for word, positions in inverted_index.items():
            for pos in positions:
                word_pos.append((pos, word))
        word_pos.sort(key=lambda x: x[0])
        return " ".join([w for _, w in word_pos])
    except Exception:
        return None

def clean_xml_abstract(xml_text):
    """Removes XML tags and decodes entities from Europe PMC / Crossref abstracts."""
    if not xml_text:
        return None
    text = html.unescape(xml_text)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split()).strip()

def calculate_relevance_rating(query_terms, title, abstract):
    """Calculates qualitative topic relevance score (60-98%) based on keyword coverage."""
    if not query_terms:
        return {
            "score_percent": 85,
            "relevance_level": "Relevant (General Scientific Topic)",
            "confidence_tier": "Standard",
            "matched_keywords": []
        }
    terms = [t.lower().strip() for t in re.split(r'[\s,\+\-]+', query_terms) if len(t.strip()) > 2]
    if not terms:
        return {
            "score_percent": 85,
            "relevance_level": "Relevant (General Scientific Topic)",
            "confidence_tier": "Standard",
            "matched_keywords": []
        }
    text_corpus = f"{title or ''} {abstract or ''}".lower()
    matches = sum(1 for t in terms if t in text_corpus)
    ratio = matches / len(terms)
    score = int(60 + (ratio * 38))
    score = min(score, 98)
    if score >= 90:
        level = "Highly Relevant (Direct Topic Match)"
        tier = "High"
    elif score >= 75:
        level = "Relevant (Related Material / Mechanism)"
        tier = "Medium"
    else:
        level = "Contextual (Background / Method Reference)"
        tier = "Standard"
    return {
        "score_percent": score,
        "relevance_level": level,
        "confidence_tier": tier,
        "matched_keywords": [t for t in terms if t in text_corpus]
    }
