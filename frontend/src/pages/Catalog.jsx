import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import Header from '../components/Header'

export default function Catalog() {
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    api.get('/catalog/products/')
      .then(res => { setProducts(res.data); setLoading(false) })
      .catch(err => { console.error('Error cargando productos:', err); setLoading(false) })
  }, [])

  if (loading) {
    return <div className="loading">Cargando catálogo… ⏳</div>
  }

  return (
    <div className="App">
      <Header />
      <div className="products-grid">
        {products.map(product => (
          <div key={product.id} className="product-card">
            <h2>{product.name}</h2>
            <p className="description">{product.description}</p>
            {product.is_digital && (
              <span className="badge badge-digital">Producto digital · sin envío</span>
            )}
            <h3 className="price">${parseInt(product.price).toLocaleString('es-CL')} CLP</h3>
            <button
              className="btn-primary"
              onClick={() => navigate('/checkout', { state: { product } })}
            >
              Comprar
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
