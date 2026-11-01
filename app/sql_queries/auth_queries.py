from sqlalchemy import text

user_email_check = text(
                    """
                        SELECT id
                        FROM users
                        WHERE LOWER(email) = :email
                    """
                )

email_insert_query = text(
                    """
                        INSERT INTO organisations
                        (name, slug, created_at) VALUES
                        (:name, :slug, :created_at)
                        RETURNING id
                    """
                )

org_member_insert_query = text(
                    """
                        INSERT INTO organisation_members
                        (org_id, user_id, role)
                        VALUES
                        (:org_id, :user_id, :role)
                    """
                )

email_token_insert_query = text(
                    """
                        INSERT INTO email_verification_tokens
                            (user_id, token_hash, expires_at)
                        VALUES
                            (:user_id, :token_hash, :expires_at)
                    """
                    )