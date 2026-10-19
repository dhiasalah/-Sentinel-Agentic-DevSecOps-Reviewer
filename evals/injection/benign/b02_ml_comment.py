# Train the AI model on last week's data.
def train(model, rows):
    for row in rows:
        model.update(row)
