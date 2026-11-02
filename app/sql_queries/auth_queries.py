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

login_query = text(
        """
            SELECT id, email, password_hash, is_active, email_verified
            FROM users
            WHERE LOWER(email) = :email
        """
        )

insert_session_query = text(
                """
                    INSERT INTO sessions (user_id, token_hash, expires_at, last_seen_at)
                    VALUES (:user_id, :token_hash, :expires_at, :last_seen_at)
                """
            )

email_verification_token_query = text(
                        """
                            UPDATE email_verification_tokens
                            SET used_at = NOW()
                            WHERE token_hash = :token_hash
                            AND used_at IS NULL
                            AND expires_at > NOW()
                            RETURNING user_id
                        """
                        )

email_verfied_upadte_query = text(
                    """
                        UPDATE users
                        SET email_verified = TRUE,
                            updated_at = NOW()
                        WHERE id = :user_id
                    """
                    )

session_query = text(
        """
            SELECT
                s.id AS session_id,
                s.user_id,
                s.expires_at,
                s.revoked_at,
                u.email,
                u.is_active,
                u.email_verified
            FROM sessions AS s
            JOIN users AS u ON u.id = s.user_id
            WHERE s.token_hash = :token_hash
            FOR UPDATE OF s
        """
        )

revoke_query = text(
            """
                UPDATE sessions
                SET revoked_at = :revoked_at
                WHERE id = :session_id
                AND revoked_at IS NULL
            """
        )

insert_session_query = text(
            """
                INSERT INTO sessions (
                    user_id,
                    token_hash,
                    expires_at,
                    last_seen_at
                )
                VALUES (
                    :user_id,
                    :token_hash,
                    :expires_at,
                    :last_seen_at
                )
            """
)

logout_session_query = text(
                """
                    UPDATE sessions
                    SET revoked_at = :revoked_at
                    WHERE token_hash = :token_hash
                    AND user_id = :user_id
                    AND revoked_at is NULL
                    RETURNING id
                """
                )