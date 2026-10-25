import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'

import Navbar from './Navbar'

describe('Navbar', () => {
  afterEach(cleanup)
  it('keeps navigation operable through the compact mobile menu', async () => {
    render(<MemoryRouter><Navbar /></MemoryRouter>)

    const menu = screen.getByRole('button', { name: 'Open navigation' })
    expect(menu).toHaveAttribute('aria-expanded', 'false')
    await userEvent.click(menu)

    expect(screen.getByRole('button', { name: 'Close navigation' })).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getAllByRole('link', { name: 'GPU network' })).toHaveLength(2)
    await userEvent.click(screen.getAllByRole('link', { name: 'GPU network' })[1])
    expect(screen.getByRole('button', { name: 'Open navigation' })).toHaveAttribute('aria-expanded', 'false')
  })

  it('marks the current workspace and keeps every existing destination reachable', () => {
    render(<MemoryRouter initialEntries={['/user/dashboard']}><Navbar /></MemoryRouter>)

    expect(screen.getByRole('link', { name: 'My jobs' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: 'New job' })).toHaveAttribute('href', '/user/submit')
    expect(screen.getByRole('link', { name: 'GPU network' })).toHaveAttribute('href', '/network')
    expect(screen.getByRole('link', { name: 'Provider console' })).toHaveAttribute('href', '/provider/dashboard')
  })
})
