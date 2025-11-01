// src/api.js

/**
 * A helper function to get the authentication headers from local storage.
 * Throws an error if the user is not logged in.
 */
const getAuthHeaders = () => {
  const accessToken = localStorage.getItem('spotify_access_token');
  if (!accessToken) {
    throw new Error("User not logged in");
  }
  return {
    'Authorization': `Bearer ${accessToken}`,
    'X-Refresh-Token': localStorage.getItem('spotify_refresh_token') || '',
    'X-Expires-At': localStorage.getItem('spotify_expires_at') || '0',
    'Content-Type': 'application/json'
  };
};

/**
 * Sends a chat message to the backend.
 * Can be called as a logged-in user or a guest.
 * @param {string} message - The user's message.
 * @returns {Promise<object>} - The JSON response from the server.
 */
export const postChatMessage = async (message) => {
  let headers = { 'Content-Type': 'application/json' };
  try {
    headers = { ...headers, ...getAuthHeaders() };
  } catch (error) {
    console.log("Sending chat message as a guest.");
  }

  const response = await fetch('/chat', {
    method: 'POST',
    headers: headers,
    body: JSON.stringify({ message })
  });

  if (!response.ok) {
    const errorData = await response.json();
    throw new Error(errorData.detail || 'Server error');
  }
  return response.json();
};

/**
 * Fetches the current user's Spotify profile from the backend.
 * @returns {Promise<object>} - The user profile JSON.
 */
export const fetchUserProfile = async () => {
    const headers = getAuthHeaders();
    const response = await fetch('/me', { headers });
    if (!response.ok) {
        throw new Error('Failed to fetch user profile');
    }
    return response.json();
};

/**
 * Fetches all pinned playlists for the current user.
 * @returns {Promise<Array>} - A list of pinned playlists.
 */
export const fetchPinnedPlaylists = async () => {
  const headers = getAuthHeaders();
  const response = await fetch('/pinned_playlists', { headers });
  if (!response.ok) {
    throw new Error('Could not fetch pinned playlists');
  }
  return response.json();
};

/**
 * Sends a request to pin a new playlist.
 * @param {string} playlistName - The name for the new playlist.
 * @param {Array} songs - The list of simplified song objects.
 * @param {string} recommendationText - The AI's recommendation text.
 */
export const pinPlaylist = async (playlistName, songs, recommendationText) => {
    const simplifiedSongs = songs.map(song => ({
        uri: song.uri, name: song.name, artists: song.artists.map(a => ({ name: a.name })),
        album: { images: song.album.images }, external_urls: { spotify: song.external_urls.spotify }
    }));

    const response = await fetch('/pin_playlist', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ 
            playlist_name: playlistName, 
            songs: simplifiedSongs, 
            recommendation_text: recommendationText 
        })
    });
    if (!response.ok) {
        throw new Error('Failed to pin playlist');
    }
};

/**
 * Sends feedback (like/dislike) for a track.
 * @param {string} trackUri - The Spotify URI of the track.
 * @param {string} feedback - The feedback, either 'like' or 'dislike'.
 */
export const sendFeedback = async (trackUri, feedback) => {
    await fetch('/feedback', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ track_uri: trackUri, feedback: feedback })
    });
};

/**
 * Fetches the detailed AI analysis for a specific song.
 * @param {string} songUri - The Spotify URI of the song.
 * @returns {Promise<object>} - The analysis data.
 */
export const fetchSongDetails = async (songUri) => {
    const response = await fetch(`/song_details/${encodeURIComponent(songUri)}`, { 
        headers: getAuthHeaders() 
    });
    if (!response.ok) {
        throw new Error('Failed to fetch song details');
    }
    return response.json();
};

/**
 * Sends a request to create a playlist in the user's Spotify account.
 * @param {string} playlistName - The desired name of the playlist.
 * @param {Array<string>} trackUris - A list of Spotify track URIs.
 * @returns {Promise<object>} - Information about the created playlist.
 */
export const createSpotifyPlaylist = async (playlistName, trackUris) => {
    const response = await fetch('/create_playlist', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ playlist_name: playlistName, track_uris: trackUris })
    });
    if (!response.ok) {
        throw new Error('Failed to create playlist');
    }
    return response.json();
};