# Copyright (C) 2023-2025 Cognizant Digital Business, Evolutionary AI.
# All Rights Reserved.
# Issued under the Academic Public License.
#
# You can be released from the terms, and requirements of the Academic Public
# License by purchasing a commercial license.
# Purchase of a commercial license is mandatory for any use of the
# neuro-san-web-client SDK Software in commercial settings.
#
# END COPYRIGHT

from typing import Any, Dict, List, Tuple

from neuro_san.internals.messages.chat_message_type import ChatMessageType
from neuro_san.message_processing.message_processor import MessageProcessor


class AgentLogProcessor(MessageProcessor):
    """
    Tells the UI there's an agent message to process.
    """

    def __init__(self, sid: str):
        """
        Constructor
        """
        self.sid: str = sid

    def process_message(
        self, chat_message_dict: Dict[str, Any], message_type: ChatMessageType
    ):
        """
        Process the message:
          - Log the message
          - Highlight the agent in the network diagram
          - Display the message in the Agents Communication panel
        :param chat_message_dict: The chat message
        :param message_type: The type of message
        """
        if message_type != ChatMessageType.AGENT:
            # This is a framework message that contains chat context, system prompts or consolidated messages.
            # Don't log them. And there's no agent to highlight in the network diagram.
            return

        # Discard empty messages
        log_text = chat_message_dict.get("text", "").strip()
        if log_text == "":
            return

        # We have a valid message. Process it.
        # Get the list of agents that participated in the message and the name of the last agent,
        # which is the one that sent the message.
        origin_chain, last_agent_name = self.get_origin(chat_message_dict)

        header = "---------- ChatMessage ----------"
        log_message = f"{header}\n{origin_chain}: {log_text}"
        # Log the message
        print(log_message)

    @staticmethod
    def get_origin(chat_message_dict) -> Tuple[str, str]:
        """
        Get the list of agents that lead to this message and the agent that produced it.
        :param chat_message_dict: The chat message
        :return: A tuple containing:
        - the list of agents involved, as a string,
        - the name of the agent that produced the message
        """
        origin: List = chat_message_dict.get("origin")
        # Convert the origin list to a string
        origin_str = " -> ".join(tool["tool"] for tool in origin)
        # the agent name is the last tool in the origin list
        last_agent_name = origin[-1].get("tool")

        return origin_str, last_agent_name
