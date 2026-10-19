# Environment Variables

This page outlines the environment variables used in the YamTrack project.

## Media Sources

| Name            | Notes                                                                                                                                                                                                                                                 |
| --------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `TMDB_API`      | The Movie Database API key for movies and TV shows. A default key is provided.                                                                                                                                                                        |
| `TMDB_NSFW`     | Default to `False`. Set to `True` to include adult content in TV and movie searches.                                                                                                                                                                  |
| `TMDB_LANG`     | TMDB metadata language. Uses a language code in ISO 639-1 (e.g., `en`). Also supports a country code in ISO 3166-1 (e.g., `en-US`). Metadata is cached for a few hours in Redis. You may need to clear the cache to see the new language immediately. |
| `MAL_API`       | MyAnimeList API key for anime and manga. A default key is provided.                                                                                                                                                                                   |
| `MAL_NSFW`      | Default to `False`. Set to `True` to include adult content in anime and manga searches from MyAnimeList.                                                                                                                                              |
| `MU_NSFW`       | Default to `False`. Set to `True` to include adult content in manga searches from MangaUpdates.                                                                                                                                                       |
| `IGDB_ID`       | IGDB API key for games. A default key is provided, but it's recommended to get your own as it has a low rate limit.                                                                                                                                   |
| `IGDB_SECRET`   | IGDB API secret for games. A default value is provided, but it's recommended to get your own as it has a low rate limit.                                                                                                                              |
| `IGDB_NSFW`     | Default to `False`. Set to `True` to include adult content in game searches.                                                                                                                                                                          |
| `HARDCOVER_API` | Hardcover API key for books. A default key is provided, but it's recommended to get your own as it has a low rate limit. Custom values must include the `Bearer ` prefix.                                                                              |
| `COMICVINE_API` | ComicVine API key for comics. A default key is provided, but it's recommended to get your own as it has a low rate limit.                                                                                                                             |

## Media Import

See [media-imports](media-imports.md).

## Redis and Django Settings

| Name               | Notes                                                                                                                                                                                                |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `REDIS_URL`        | Default to `redis://localhost:6379`. Set this to your Redis server URL, in the format of `redis://{service}:{port}`. In the Docker Compose examples this is `redis://redis:6379`. If Yamtrack shares a Docker network with another container or service named `redis`, use the Yamtrack Redis container name instead: `redis://yamtrack-redis:6379`. |
| `CELERY_REDIS_URL` | Default to the value of `REDIS_URL`. Set this to your Redis server URL for Celery if you need a different value than `REDIS_URL`.                                                                    |
| `REDIS_PREFIX`     | Optional prefix for Redis keys and channels to enable isolation when sharing a Redis instance across multiple applications. Useful for ACL-based permission control.                                 |
| `SECRET`           | [Secret key](https://docs.djangoproject.com/en/stable/ref/settings/#secret-key) used for cryptographic signing. Should be a random string.                                                           |
| `URLS`             | Shortcut to set both the `CSRF` and `ALLOWED_HOSTS` settings. Comma-separated list of URLs (e.g., `https://yamtrack.mydomain.com`).                                                                  |
| `ALLOWED_HOSTS`    | Comma-separated list of host/domain names that this Django site can serve (e.g., `yamtrack.mydomain.com`). Default to `*` for all hosts.                                                             |
| `CSRF`             | Comma-separated list of trusted origins for `POST` requests when using reverse proxies (e.g., `https://yamtrack.mydomain.com`).                                                                      |
| `REGISTRATION`     | Default to `True`. Set to `False` to disable user registration.                                                                                                                                      |
| `DEBUG`            | Default to `False`. Set to `True` for debugging.                                                                                                                                                     |
| `ADMIN_ENABLED`    | Default to `False`. Set to `True` to enable the Django admin interface.                                                                                                                              |
| `TRACK_TIME`       | Default to `True`. Set to `False` to disable time tracking in Yamtrack.                                                                                                                              |

## User and System Configuration

| Name                            | Notes                                                                                                                                                                 |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `PUID`                          | User ID for the app. Default to `1000`.                                                                                                                               |
| `PGID`                          | Group ID for the app. Default to `1000`.                                                                                                                              |
| `TZ`                            | Timezone (e.g., `Europe/Berlin`). Default to `UTC`.                                                                                                                   |
| `WEB_CONCURRENCY`               | Number of web server processes. Default to `1`.                                                                                                                       |
| `SOCIAL_PROVIDERS`              | Comma-separated list of social authentication providers to enable (e.g., `allauth.socialaccount.providers.openid_connect,allauth.socialaccount.providers.github`).    |
| `SOCIALACCOUNT_PROVIDERS`       | JSON configuration for social providers. See the [Docs](social-auth.md) for an OIDC configuration example.                                                            |
| `ACCOUNT_DEFAULT_HTTP_PROTOCOL` | Protocol for social providers. If your `redirect_uri` in OIDC config is `https`, set this to `https`. Default is determined based on your `CSRF` settings.            |
| `ACCOUNT_LOGOUT_REDIRECT_URL`   | Absolute URL to redirect users after logout. Useful for OpenID Connect providers to ensure complete logout from the external authentication provider.                 |
| `SOCIALACCOUNT_ONLY`            | Default to `False`. Set to `True` to disable local authentication when using social authentication only.                                                              |
| `REDIRECT_LOGIN_TO_SSO`         | Default to `False`. Set to `True` to automatically redirect (using JavaScript) to the SSO provider when there's only one available. Useful for single sign-on setups. |
| `YAMTRACK_AUTO_LOGIN_USERNAME`  | Default to `None`, which disables this feature. Specify a username to automatically login with the selected user. The user needs to be existing and active.           |

## Celery Health Check

| Name                              | Notes                                                                                                           |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `HEALTHCHECK_CELERY_PING_TIMEOUT` | Default to `1`. Increases the timeout for the health check ping to Celery. This is useful for slow connections. |

## PostgreSQL Environment Variables (YamTrack Container)

| Name          | Notes                                                                                                    |
| ------------- | -------------------------------------------------------------------------------------------------------- |
| `DB_HOST`     | The hostname or IP address of the PostgreSQL server. If not set, SQLite is used as the default database. |
| `DB_PORT`     | The port number on which the PostgreSQL server is listening.                                             |
| `DB_NAME`     | The name of the database to connect to.                                                                  |
| `DB_USER`     | The username used to authenticate with the PostgreSQL server.                                            |
| `DB_PASSWORD` | The password for the specified user.                                                                     |

**Note:** Check the example `docker-compose.postgres.yml` in the root directory of the repo for a PostgreSQL configuration example.

### External PostgreSQL database with SSL (YamTrack Container)

| Name               | Notes                                                                                                                                                                                                                                         |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `DB_SSL_MODE`      | Determines whether or with what priority a secure SSL TCP/IP connection will be negotiated with the server. See [the official documentation](https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNECT-SSLMODE).               |
| `DB_SSL_CERT_MODE` | Determines whether a client certificate may be sent to the server, and whether the server is required to request one. See [the official documentation](https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNECT-SSLCERTMODE). |

## Sonarr Integration

Sonarr is an optional, manual-only integration. Setting `SONARR_URL` and `SONARR_API_KEY` makes an **Add to Sonarr** button appear on the TV details page, on each season page, and on every TV card of the home page. Nothing is ever sent to Sonarr automatically: tracking or importing a show never touches it.

| Name                     | Notes                                                                                                                                                                                                                                                             |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `SONARR_URL`             | Base URL of your Sonarr instance (e.g. `http://sonarr:8989`). When Sonarr runs directly on the Docker host rather than in a container, use `http://host.docker.internal:8989`. Trailing slashes are ignored. Empty (the default) disables the integration.           |
| `SONARR_API_KEY`         | Sonarr API key, found under Settings → General → Security. Can be provided as `SONARR_API_KEY_FILE` instead. Both `SONARR_URL` and `SONARR_API_KEY` are required for the button to show up.                                                                          |
| `SONARR_ENABLED`         | Read-only, derived from `SONARR_URL` and `SONARR_API_KEY`. It is exported to the UI so the button and the Search toggle can be hidden when the integration is not configured. Set it indirectly, not directly.                                                       |
| `SONARR_QUALITY_PROFILE` | Quality profile to add a show with, by exact name (e.g. `4K o 1080p - Upgrades Allowed`) or by numeric id (e.g. `7`). Empty (the default) uses the first profile Sonarr returns.                                                                                    |
| `SONARR_ROOT_FOLDER`     | Root folder for new shows, either the id or the path (e.g. `D:/Series`). Empty (the default) uses the first root folder Sonarr reports. The value is matched against Sonarr's own folders ignoring slash direction and case, so `D:/Series` and `D:\Series` are equal. |
| `SONARR_LANGUAGE_PROFILE`| Language profile for Sonarr v3 only (e.g. `English`). Leave empty to leave the field untouched. Ignored on Sonarr v4, which dropped language profiles.                                                                                                             |
| `SONARR_SEARCH_ON_ADD`   | Default to `False`. Sets the initial state of the **Search** checkbox next to the Add to Sonarr button. `False` only registers the show in Sonarr without grabbing anything; `True` pre-checks the box so a click also queues a search.                              |

**What the buttons do.** From a whole series the show is added with every season but the specials monitored; from a season page only that season is monitored. If the show is already in Sonarr, the whole series button fills in any missing seasons and the season button monitors just that season.

On the home page, TV cards (a whole show, a season, or an episode) trade their **Activity History** button for an **Add to Sonarr** button, and on those cards the action also searches: it grabs whatever Sonarr is missing, so a mis-click downloads episodes. The button follows the tracked item, so tracking a season monitors that season and tracking an episode monitors the season it belongs to. The Activity History button is kept for the other media types, which Sonarr cannot take.

On the details and season pages the Search checkbox is a per-click choice and defaults to `SONARR_SEARCH_ON_ADD`.

## Radarr Integration

Radarr is an optional, manual-only integration. Setting `RADARR_URL` and `RADARR_API_KEY` makes an **Add to Radarr** button appear on the movie details page and on every movie card of the home page. Nothing is ever sent to Radarr automatically: tracking or importing a movie never touches it.

| Name                          | Notes                                                                                                                                                                                                                                                             |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `RADARR_URL`                  | Base URL of your Radarr instance (e.g. `http://radarr:7878`). When Radarr runs directly on the Docker host rather than in a container, use `http://host.docker.internal:7878`. Trailing slashes are ignored. Empty (the default) disables the integration.         |
| `RADARR_API_KEY`              | Radarr API key, found under Settings → General → Security. Can be provided as `RADARR_API_KEY_FILE` instead. Both `RADARR_URL` and `RADARR_API_KEY` are required for the button to show up.                                                                        |
| `RADARR_ENABLED`              | Read-only, derived from `RADARR_URL` and `RADARR_API_KEY`. It is exported to the UI so the button and the Search toggle can be hidden when the integration is not configured. Set it indirectly, not directly.                                                     |
| `RADARR_QUALITY_PROFILE`      | Quality profile to add a movie with, by exact name (e.g. `HD - 720p/1080p`) or by numeric id (e.g. `7`). Empty (the default) uses the first profile Radarr returns.                                                                                                 |
| `RADARR_ROOT_FOLDER`          | Root folder for new movies, either the id or the path (e.g. `D:/Movies`). Empty (the default) uses the first root folder Radarr reports. The value is matched against Radarr's own folders ignoring slash direction and case, so `D:/Movies` and `D:\Movies` are equal. |
| `RADARR_MINIMUM_AVAILABILITY` | Minimum availability a movie must reach before Radarr grabs it: `announced`, `inCinemas`, `released` or `preDB`. Defaults to `released`, so nothing is grabbed before a movie is actually out.                                                                     |
| `RADARR_SEARCH_ON_ADD`        | Default to `False`. Sets the initial state of the **Search** checkbox next to the Add to Radarr button. `False` only registers the movie in Radarr without grabbing anything; `True` pre-checks the box so a click also queues a search.                             |

**What the buttons do.** The button adds the movie to Radarr with the configured quality profile and root folder. If the movie is already in Radarr it is left alone, unless it was unmonitored, in which case monitoring is turned on. There is no bulk "add everything" action: only the button does anything, and only when clicked.

On the home page, movie cards trade their **Activity History** button for an **Add to Radarr** button. The Activity History button is kept for the other media types, which Radarr cannot take.

On the details page the Search checkbox is a per-click choice and defaults to `RADARR_SEARCH_ON_ADD`.

## Docker Secrets Support

YamTrack supports reading sensitive configuration values from Docker secrets files. The following environment variables can alternatively be provided as secrets:

| Environment Variable      | Secret File Equivalent         |
| ------------------------- | ------------------------------ |
| `SECRET`                  | `SECRET_FILE`                  |
| `DB_NAME`                 | `DB_NAME_FILE`                 |
| `DB_USER`                 | `DB_USER_FILE`                 |
| `DB_PASSWORD`             | `DB_PASSWORD_FILE`             |
| `TMDB_API`                | `TMDB_API_FILE`                |
| `MAL_API`                 | `MAL_API_FILE`                 |
| `IGDB_ID`                 | `IGDB_ID_FILE`                 |
| `IGDB_SECRET`             | `IGDB_SECRET_FILE`             |
| `HARDCOVER_API`           | `HARDCOVER_API_FILE`           |
| `COMICVINE_API`           | `COMICVINE_API_FILE`           |
| `TRAKT_API`               | `TRAKT_API_FILE`               |
| `SONARR_API_KEY`          | `SONARR_API_KEY_FILE`          |
| `RADARR_API_KEY`          | `RADARR_API_KEY_FILE`          |
| `SIMKL_ID`                | `SIMKL_ID_FILE`                |
| `SIMKL_SECRET`            | `SIMKL_SECRET_FILE`            |
| `SOCIALACCOUNT_PROVIDERS` | `SOCIALACCOUNT_PROVIDERS_FILE` |

## Host under subpath

| Name       | Notes                                                                                                                  |
| ---------- | ---------------------------------------------------------------------------------------------------------------------- |
| `BASE_URL` | To host YamTrack under a subpath like `https://example.com/yamtrack`, set this to `/yamtrack`, without trailing slash. |

## Self-signed certificates

| Name                 | Notes                                                                                                                                                                                                                                                                 |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `REQUESTS_CA_BUNDLE` | Path to a custom CA certificate bundle file for SSL verification. Useful for self-hosted authentication providers with self-signed certificates (e.g., `/etc/ssl/certs/ca-certificates.crt`). This requires the CA certificate to be present in the host's CA bundle. |
