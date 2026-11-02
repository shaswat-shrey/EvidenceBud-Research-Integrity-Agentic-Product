from sqlalchemy import text

chat_query = text(
                """
                    SELECT c.id
                    FROM chats c
                    JOIN projects p ON p.id = c.project_id
                    WHERE c.id = :chat_id
                    AND c.archived_at IS NULL
                    AND p.archived_at IS NULL
                    AND (
                        p.owner_user_id = :user_id
                        OR p.organisation_id IN (
                        SELECT om.org_id
                        FROM organisation_members om
                        WHERE om.user_id = :user_id
                        )
                    )
                """
                )

insert_messages_query = text(
                """
                    INSERT INTO chat_messages (
                        chat_id,
                        author_user_id,
                        role,
                        content
                    )
                    VALUES (
                        :chat_id,
                        :user_id,
                        'user',
                        :content
                    )
                    RETURNING id, chat_id, author_user_id, role, content,
                            metadata, created_at
                """
            )