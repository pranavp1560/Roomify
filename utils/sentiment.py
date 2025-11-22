import nltk
from nltk.sentiment.vader import SentimentIntensityAnalyzer

# Ensure VADER lexicon is available (important for Render)
try:
    nltk.data.find('sentiment/vader_lexicon.zip')
except LookupError:
    nltk.download('vader_lexicon')

sia = SentimentIntensityAnalyzer()

def analyze_sentiment(text):
    return sia.polarity_scores(text)

# Make sure this is downloaded once during setup
# nltk.download("vader_lexicon")

sia = SentimentIntensityAnalyzer()

def analyze_sentiment(review_text, rating=None):
    """Combine text sentiment + rating sentiment into one score."""

    # Text sentiment
    text_score = sia.polarity_scores(review_text)["compound"]

    # Rating sentiment (1–5 mapped to -1 to +1)
    rating_score = 0
    if rating:
        try:
            rating_val = int(rating)
            rating_score = (rating_val - 3) / 2.0  
        except:
            rating_score = 0

    final_score = (text_score + rating_score) / 2.0

    if final_score >= 0.05:
        sentiment = "positive"
    elif final_score <= -0.05:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    return {
        "sentiment": sentiment,
        "final_score": final_score,
        "text_score": text_score,
        "rating_score": rating_score
    }

