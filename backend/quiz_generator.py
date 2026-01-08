import wikipedia
import random
import re
import nltk

# Download NLTK data if not already
nltk.download("punkt", quiet=True)
nltk.download("stopwords", quiet=True)
nltk.download("averaged_perceptron_tagger", quiet=True)
nltk.download("wordnet", quiet=True)
nltk.download("omw-1.4", quiet=True)

from nltk.corpus import stopwords, wordnet
from nltk.tokenize import sent_tokenize, word_tokenize

stop_words = set(stopwords.words("english"))

def clean_text(text):
    text = re.sub(r'\[[0-9]*\]', '', text)  # remove [1], [2]
    text = re.sub(r'\s+', ' ', text)
    return text

def get_wiki_content(topic):
    try:
        # Search for closest matching Wikipedia title
        search_results = wikipedia.search(topic)
        if not search_results:
            return None
        page_title = search_results[0]
        page = wikipedia.page(page_title, auto_suggest=False, redirect=True)
        summary = page.content
    except:
        try:
            summary = wikipedia.summary(topic, sentences=5, auto_suggest=False, redirect=True)
        except:
            return None
    return clean_text(summary)

def get_distractors(answer):
    distractors = set()
    for syn in wordnet.synsets(answer):
        for lemma in syn.lemmas():
            w = lemma.name().replace('_', ' ')
            if w.lower() != answer.lower():
                distractors.add(w)
    return list(distractors)[:3]

def generate_quiz(topic, num_questions=5):
    text = get_wiki_content(topic)
    if not text:
        return {"error": f"Topic '{topic}' not found!"}

    sentences = sent_tokenize(text)
    quiz = []

    for sentence in sentences[:num_questions * 5]:  # try more sentences
        words = [w for w in word_tokenize(sentence) if w.isalpha()]

        # POS tagging to select nouns/proper nouns
        tags = nltk.pos_tag(words)
        keywords = [w for w, t in tags if t in ("NN", "NNP", "NNS") and w.lower() not in stop_words]

        if not keywords:
            continue

        answer = random.choice(keywords)
        question = sentence.replace(answer, "_____")

        # Generate distractors
        distractors = get_distractors(answer)
        # fallback: pick random words if WordNet fails
        if len(distractors) < 3:
            remaining = [w for w in set(words) if w.lower() != answer.lower()]
            distractors += random.sample(remaining, min(3 - len(distractors), len(remaining)))

        options = distractors + [answer]
        random.shuffle(options)

        quiz.append({
            "question": question,
            "options": options,
            "answer": answer
        })

        if len(quiz) >= num_questions:
            break

    return quiz
