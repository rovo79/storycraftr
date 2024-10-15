import os
import glob
import time
from dotenv import load_dotenv
from openai import OpenAI
from rich.console import Console
from rich.progress import Progress

load_dotenv()

client = OpenAI()
console = Console()


# Function to load all Markdown files from the book's directory and subdirectories
def load_markdown_files(book_name):
    """Load all Markdown files from the book's directory and subdirectories."""
    console.print(
        f"[bold blue]Loading all Markdown files from '{book_name}'...[/bold blue]"
    )  # Progress message
    md_files = glob.glob(f"{book_name}/**/*.md", recursive=True)
    console.print(
        f"[bold green]Loaded {len(md_files)} Markdown files.[/bold green]"
    )  # Success message
    return md_files


# Function to delete an existing assistant
def delete_assistant(book_name):
    name = book_name.split("/")[-1]
    console.print(
        f"[bold blue]Checking if assistant '{name}' exists for deletion...[/bold blue]"
    )  # Progress message
    assistants = client.beta.assistants.list()
    for assistant in assistants.data:
        if assistant.name == name:
            console.print(f"Deleting assistant {name}...")
            client.beta.assistants.delete(assistant_id=assistant.id)
            console.print(
                f"[bold green]Assistant {name} deleted successfully.[/bold green]"
            )  # Success message
            break


# Function to create or get an assistant
def create_or_get_assistant(book_name):
    name = book_name.split("/")[-1]
    console.print(
        f"[bold blue]Searching for existing assistant '{name}'...[/bold blue]"
    )  # Progress message
    assistant = None
    assistants = client.beta.assistants.list()
    for assistant in assistants.data:
        if assistant.name == name:
            console.print(
                f"[bold yellow]Assistant {name} already exists.[/bold yellow]"
            )  # Success message
            return assistant

    # Step 1. Create a vector store for the book
    console.print(
        f"[bold blue]Creating vector store for '{book_name}'...[/bold blue]"
    )  # Progress message
    vector_store = client.beta.vector_stores.create(name=f"{book_name} Docs")

    # Step 2. Upload Knowledge (Markdown files)
    console.print(
        f"[bold blue]Uploading knowledge from '{book_name}'...[/bold blue]"
    )  # Progress message
    md_files = load_markdown_files(book_name)

    file_streams = [open(file_path, "rb") for file_path in md_files]

    file_batch = client.beta.vector_stores.file_batches.upload_and_poll(
        vector_store_id=vector_store.id, files=file_streams
    )

    while file_batch.status == "queued" or file_batch.status == "in_progress":
        console.print(
            f"[bold yellow]{file_batch.status}...[/bold yellow]"
        )  # Progress message
        time.sleep(1)

    # Step 3. Create the Assistant
    console.print(
        f"[bold blue]Reading behavior instructions...[/bold blue]"
    )  # Progress message
    with open("behaviors/default.txt", "r") as file:
        instructions = file.read()

    console.print(
        f"[bold blue]Creating assistant '{name}'...[/bold blue]"
    )  # Progress message
    assistant = client.beta.assistants.create(
        instructions=instructions,
        name=name,
        tools=[{"type": "code_interpreter"}, {"type": "file_search"}],
        model="gpt-4o",
    )

    # Associate the assistant with the vector store
    console.print(
        f"[bold blue]Associating assistant '{name}' with vector store...[/bold blue]"
    )  # Progress message
    assistant = client.beta.assistants.update(
        assistant_id=assistant.id,
        tool_resources={"file_search": {"vector_store_ids": [vector_store.id]}},
    )

    console.print(
        f"[bold green]Assistant '{name}' created successfully.[/bold green]"
    )  # Success message

    return assistant


# Function to create a message in a thread and handle async processing
def create_message(thread_id, content, assistant, file_path=None):
    """
    Create a message in the thread and process it asynchronously.

    Parameters:
        thread_id (str): The ID of the thread where the message will be created.
        content (str): The content of the message.
        assistant (object): The assistant object with an ID.
        file_path (str, optional): The path to a file to attach as an attachment. Defaults to None.

    Returns:
        str: The text content of the last message returned by the assistant.
    """

    console.print(
        f"[bold blue]Creating message in thread {thread_id}...[/bold blue]"
    )  # Progress message

    # Prepare the base prompt
    if file_path and os.path.exists(file_path):
        console.print(
            f"[bold blue]Reading content from {file_path} for improvement...[/bold blue]"
        )  # Progress message
        with open(file_path, "r", encoding="utf-8") as f:
            file_content = f.read()
            # Append the file content to the prompt asking for improvement
            content = (
                f"{content}\n\nHere is the existing content to improve:\n{file_content}"
            )
    else:
        console.print(
            f"[bold blue]Using provided prompt to generate new content...[/bold blue]"
        )  # Progress message

    # Prepare the message payload
    message_payload = {"thread_id": thread_id, "role": "user", "content": content}

    # Create the message in the thread
    client.beta.threads.messages.create(**message_payload)

    # Start the assistant run
    run = client.beta.threads.runs.create(
        thread_id=thread_id, assistant_id=assistant.id
    )
    console.print(
        "[bold blue]Sending prompt to OpenAI API...[/bold blue]"
    )  # Progress message

    with Progress() as progress:
        task = progress.add_task("[cyan]Waiting run to finalize...", total=50)

        # Simular el ciclo de espera del estado
        while run.status == "queued" or run.status == "in_progress":
            run = client.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run.id,
            )
            # Simular progreso de la barra (puedes ajustar la lógica según tu caso)
            progress.update(task, advance=1)
            time.sleep(0.5)  # Esperar antes de volver a comprobar el estado del run

    console.print(
        f"[bold green]Generated content received.[/bold green]"
    )  # Success message

    # Retrieve the list of messages in the thread and return the last message content
    messages = client.beta.threads.messages.list(thread_id=thread_id)

    return messages.data[0].content[0].text.value


# Function to get a new thread
def get_thread():
    console.print(f"[bold blue]Creating new thread...[/bold blue]")  # Progress message
    return client.beta.threads.create()


# Function to update the assistant's knowledge with new files
def update_agent_files(book_name, assistant):
    delete_assistant(book_name)
    create_or_get_assistant(book_name)

    console.print(
        f"[bold green]Files updated successfully in assistant '{assistant.name}'.[/bold green]"
    )  # Success message
