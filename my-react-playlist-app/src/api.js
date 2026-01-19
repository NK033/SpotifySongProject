// src/api.js

// ✅ 1. Read URL from .env (User's original logic)
const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/**
 * A helper function to get the authentication headers from local storage.
 */
const getAuthHeaders = () => {
  const accessToken = localStorage.getItem('spotify_access_token');
  if (!accessToken) {
    // Changing to console.warn to prevent crash loops if not logged in
    console.warn("User not logged in (No Token)"); 
    // throw new Error("User not logged in"); 
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
 */
export const sendMessageToChatbot = async (message, intent = null) => {
  let headers = { 'Content-Type': 'application/json' };
  try {
    headers = { ...headers, ...getAuthHeaders() };
  } catch (error) {
    console.log("Sending chat message as a guest.");
  }

  const response = await fetch(`${BASE_URL}/chat`, {
    method: 'POST',
    headers: headers,
    body: JSON.stringify({ message, intent })
  });

  if (!response.ok) {
    const errorData = await response.json();
    throw new Error(errorData.detail || 'Server error');
  }
  return response.json();
};
export const postChatMessage = sendMessageToChatbot;

/**
 * Fetches the current user's Spotify profile.
 */
export const fetchUserProfile = async () => {
    const headers = getAuthHeaders();
    const response = await fetch(`${BASE_URL}/me`, { headers });
    if (!response.ok) {
        throw new Error('Failed to fetch user profile');
    }
    return response.json();
};

/**
 * Fetches pinned playlists.
 */
export const getPinnedPlaylistsAPI = async () => {
  const headers = getAuthHeaders();
  const response = await fetch(`${BASE_URL}/pinned_playlists`, { headers });
  if (!response.ok) {
    throw new Error('Could not fetch pinned playlists');
  }
  return response.json();
};
export const fetchPinnedPlaylists = getPinnedPlaylistsAPI;

/**
 * Pins a new playlist.
 */
export const pinPlaylistAPI = async (playlistName, songs, recommendationText) => {
    const simplifiedSongs = songs.map(song => ({
        uri: song.uri, name: song.name, artists: song.artists.map(a => ({ name: a.name })),
        album: { images: song.album.images }, external_urls: { spotify: song.external_urls.spotify }
    }));

    const response = await fetch(`${BASE_URL}/pin_playlist`, {
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
export const pinPlaylist = pinPlaylistAPI;

/**
 * Sends feedback (like/dislike).
 */
export const sendFeedbackAPI = async (trackUri, feedback) => {
    await fetch(`${BASE_URL}/feedback`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ track_uri: trackUri, feedback: feedback })
    });
};
export const sendFeedback = sendFeedbackAPI;

/**
 * Fetches song details.
 */
export const getSongDetailsAPI = async (songUri) => {
    const response = await fetch(`${BASE_URL}/song_details/${encodeURIComponent(songUri)}`, {
        headers: getAuthHeaders() 
    });
    if (!response.ok) {
        throw new Error('Failed to fetch song details');
    }
    return response.json();
};
export const fetchSongDetails = getSongDetailsAPI;

/**
 * Creates a Spotify playlist.
 */
export const createPlaylistAPI = async (playlistName, trackUris) => {
    const response = await fetch(`${BASE_URL}/create_playlist`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ playlist_name: playlistName, track_uris: trackUris })
    });
    if (!response.ok) {
        throw new Error('Failed to create playlist');
    }
    return response.json();
};
export const createSpotifyPlaylist = createPlaylistAPI;

/**
 * Deletes a pinned playlist.
 */
export const deletePinnedPlaylistAPI = async (pinId) => {
  const response = await fetch(`${BASE_URL}/pinned_playlists/${pinId}`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });
  if (!response.ok) {
    throw new Error('Failed to delete pinned playlist');
  }
  return { success: true };
};
export const deletePinnedPlaylist = deletePinnedPlaylistAPI;

/**
 * Updates a pinned playlist.
 */
export const updatePinnedPlaylistAPI = async (pinId, newName, songs) => {
  const response = await fetch(`${BASE_URL}/pinned_playlists/${pinId}`, {
    method: 'PUT',
    headers: getAuthHeaders(),
    body: JSON.stringify({
      playlist_name: newName,
      songs: songs 
    })
  });
  if (!response.ok) {
    throw new Error('Failed to update playlist');
  }
  return { success: true };
};
export const updatePinnedPlaylist = updatePinnedPlaylistAPI;

/**
 * Summarizes a playlist.
 */
export const summarizePlaylistAPI = async (songUris) => {
  const response = await fetch(`${BASE_URL}/summarize_playlist`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ song_uris: songUris })
  });
  if (!response.ok) {
    throw new Error('Failed to summarize playlist');
  }
  return response.json(); 
};
export const summarizePlaylist = summarizePlaylistAPI;

/**
 * Fetches dynamic suggested prompts.
 */
export const getSuggestedPromptsAPI = async () => {
  try {
    const headers = getAuthHeaders();
    const response = await fetch(`${BASE_URL}/suggested_prompts`, { headers });
    if (!response.ok) {
      throw new Error('Could not fetch suggestions');
    }
    return response.json();
  } catch (error) {
    console.warn("Could not fetch dynamic prompts, using default.", error.message);
    return { prompts: [ '🎵 แนะนำเพลงส่วนตัวให้หน่อย', '📈 ขอเพลงฮิตติดชาร์ต', '🎧 หาเพลงเศร้าๆ' ] };
  }
};
export const fetchSuggestedPrompts = getSuggestedPromptsAPI;

// ==========================================
// ✅ NEW FUNCTIONS FOR FEEDBACK HISTORY
// ==========================================

export const getFeedbackHistoryAPI = async () => {
    const headers = getAuthHeaders();
    const response = await fetch(`${BASE_URL}/feedback/history`, { headers });
    if (!response.ok) {
        throw new Error('Failed to fetch feedback history');
    }
    return response.json();
};

export const deleteFeedbackAPI = async (trackUri) => {
    const headers = getAuthHeaders();
    const response = await fetch(`${BASE_URL}/feedback?track_uri=${encodeURIComponent(trackUri)}`, { 
        method: 'DELETE',
        headers 
    });
    if (!response.ok) {
        throw new Error('Failed to delete feedback');
    }
    return response.json();
};

export const getFeedbackStatusAPI = async () => {
    const headers = getAuthHeaders();
    const response = await fetch(`${BASE_URL}/feedback/status`, { headers });
    if (!response.ok) {
        throw new Error('Failed to fetch feedback status');
    }
    return response.json();
};